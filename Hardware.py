import os
import time
import logging
import serial
import traceback
from threading import Lock, Event
from queue import SimpleQueue
import re
from enum import auto, IntEnum

from PyQt5.QtCore import Qt, QSize, QTimer, QObject, QThread, pyqtSignal

log = logging.getLogger('')

class Filler(QObject):

    finished = pyqtSignal()

    # -------------------------------------------------------------------------
    def __init__(self, simulate=False, *args, **kwargs):

        QObject.__init__(self, *args, **kwargs)

        # Flag to indicate we are in a simulation mode
        self.simulate = simulate
        self.simulatedPressure = 0.0
        self.simulatedWeight = 0.0
        self.simulatedFootswitchLatched = False
        self.simulatedStopswitch = False
        self.simulatedStable = False

        # Conversion factors
        self.PSIperCount = None
        self.PSIintercept = None

        # Serial interface
        self.ser = None

        # Detect which comm device is connected (ACM0 for real system, USB0 for dev VM)
        device1 = '/dev/ttyACM0'
        device2 = '/dev/ttyUSB0'
        if os.path.exists(device1):
            self.port = device1
        elif os.path.exists(device2):
            self.port = device2
        else:
            raise Exception('Serial device not detected!')

        self.baudrate = 19200
        self.lastmessage = 0

        # Interface to callers
        self.requests = SimpleQueue()
        self._weight = 0.0
        self._weights = list()
        self.maxweights = 30 # Use the last 30 values in the calculation
        self._stopswitch = False
        self._footswitch = False
        self._footswitchLatched = False
        self.pressureRaw = 0

        # Task properties
        self.tickrate = 0.005
        self._stop = Event()
        self._stop.clear()
        self.lock = Lock()

    # -------------------------------------------------------------------------
    def countsToPSI(self, counts):
        """Convert A to D counts into a PSI value """

        # Pressure is provided as a voltage across a resistor converted to A to D counts.

        # Calculate the PSI slope/intercept from A to D counts
        if self.PSIperCount is None:

            # (measured empirically)
            # Resistor             = 216 ohm
            R = 216

            # (default value, could be measured)
            # Reference voltage    = 5 V
            Vref = 5.0

            # A to D range         = 10 bits = 1024 counts
            adRange = 2 ** 10

            # A to D counts / volt = AtoD (1023) / Vref (5) = 204.8
            countsPerVolt = adRange / Vref

            # (measured empirically)
            # Current at 0psi      = 0.004 A
            # Current at 30psi     = 0.020 A
            I0psi = 0.004
            I30psi = 0.020

            # Voltage at 0psi      = 0.004A * 216 = 0.86V
            # Voltage at 30psi     = 0.020A * 216 = 4.32V
            V0psi = I0psi * R
            V30psi = I30psi * R

            # AtoD counts at 0psi  = 0.86V * 204.8 = 177 counts
            # AtoD counts at 30psi = 4.32V * 204.8 = 885 counts
            C0psi = V0psi * countsPerVolt
            C30psi = V30psi * countsPerVolt

            # PSI / count          = ((30-0) / (885-177)) = 0.0424 psi/count
            self.PSIperCount = (30-0) / (C30psi - C0psi)

            # x1, y1 = 177 counts, 0 psi
            # y - y1 = m(x - x1)
            # y - 0  = m(x - 177)
            # y      = mx - (m*177)
            # PSI at 0 counts = 0 -(0.0424 * 177) = -7.5 psi
            self.PSIintercept = -(self.PSIperCount * C0psi)

        # Counts to PSI equation:
        #
        # PSI = (0.0424 psi/count) * count + (-7.5 psi)
        psi = self.PSIperCount * counts + self.PSIintercept

        return psi

    # -------------------------------------------------------------------------
    @property
    def connected(self):
        # If we have received a message in the last second, we are "connected"
        now = time.time()
        return (now - self.lastmessage < 1)

    @property
    def weight(self):
        if self.simulate:
            return self.simulatedWeight

        with self.lock:
            return self._weight

    @weight.setter
    def weight(self, val):
        with self.lock:
            self._weight = val
            self._weights.append(val)

            # Trim the array to the last 30 weights
            while len(self._weights) > self.maxweights:
                self._weights = self._weights[1:]

    @property
    def stable(self):
        if self.simulate:
            return self.simulatedStable

        with self.lock:

            # Once we have enough values to work with...
            if len(self._weights) > 2:

                # The weight value is stable if the last 10 vals are within 0.1g of the most recent value
                latest = self._weights[-1]

                for val in self._weights[:-1]:
                    if val > (latest + 0.1):
                        return False
                    if val < (latest - 0.1):
                        return False

            return True

    @property
    def footswitch(self):
        with self.lock:
            return self._footswitch
    @footswitch.setter
    def footswitch(self, val):
        with self.lock: self._footswitch = val

    @property
    def footswitchLatched(self):
        if self.simulate:
            return self.simulatedFootswitchLatched
        with self.lock:
            return self._footswitchLatched

    @footswitchLatched.setter
    def footswitchLatched(self, val):
        with self.lock:
            self._footswitchLatched = val
            self.simulatedFootswitchLatched = val

    @property
    def stopswitch(self):
        if self.simulate:
            return self.simulatedStopswitch
        with self.lock:
            return self._stopswitch
    @stopswitch.setter
    def stopswitch(self, val):
        with self.lock: self._stopswitch = val

    @property
    def pressure(self):
        if self.simulate:
            return self.simulatedPressure

        # Convert the raw pressure value into PSI
        with self.lock:
            p = self.pressureRaw

            # Clip the pressure at minimum/maximum
            if p > 1023:
                p = 1023
            if p < 0:
                p = 0

            return self.countsToPSI(p)

    # -------------------------------------------------------------------------
    def simulatePressure(self, val):
        self.simulate = True
        self.simulatedPressure = val

    def simulateWeight(self, val):
        self.simulate = True
        self.simulatedWeight = val
        self.simulatedStable = False

    def simulateStable(self, val):
        self.simulate = True
        self.simulatedStable = val

    def clearStable(self):
        self.simulatedStable = False

    def simulateFootswitch(self, val):
        self.simulate = True
        self.simulatedFootswitchLatched = val

    def simulateStopSwitch(self, val=False, toggle=False):
        self.simulate = True
        if toggle:
            self.simulatedStopswitch = not self.simulatedStopswitch
        else:
            self.simulatedStopswitch = val

    # -------------------------------------------------------------------------
    def setup(self, port, baudrate):
        """Set the properties of the serial port"""
        self.port = port
        self.baudrate = baudrate

    # -------------------------------------------------------------------------
    class TASKS(IntEnum):
        """Task requests that can be made from other threads"""
        ABORT      = 0
        PRESSURIZE = auto()
        VENT       = auto()
        DISPENSE   = auto()

    def request(self, task, param=None):
        """Create a request event to the filler I/O"""
        if task in self.TASKS:
            self.requests.put((task,param), block=False)
        else:
            log.critical(f'Unknown task requested of filler hardware: {task}')

    def getRequest(self):
        """Get the most recent request"""
        if not self.requests.empty():
            task, param = self.requests.get(block=False, timeout=0)
        else:
            task = None
            param = None

        return task, param

    # -------------------------------------------------------------------------
    def read(self):
        """Read from the serial port and parse the fields out"""
        if self.ser is None:
            try:
                self.ser = serial.Serial(self.port, self.baudrate, timeout=0.05)
            except serial.SerialException:
                return

        # Read a line from the Arduino
        s = self.ser.readline()

        if len(s) > 0:
            self.lastmessage = time.time()

            # Data Format example:  "+    0.00g  ;194;s;f"
            match = re.match('([-+ ]*)\s*(\d+\.\d+)g\s*;(\d+);([sS]);([fF])', s.decode('UTF-8'))
            if match:
                posneg = match.groups()[0].strip()
                weightStr = match.groups()[1]
                pressureStr = match.groups()[2]
                stopswitchStr = match.groups()[3]
                footswitchStr = match.groups()[4]

                # Decode the weight
                try:
                    self.weight = float(posneg + weightStr)
                except ValueError as e:
                    log.critical(f'Unable to format weight strings: "{posneg}" "{weightStr}"')
                    self.weight = -99.99

                # Decode the pressure
                try:
                    self.pressureRaw = int(pressureStr)
                except ValueError as e:
                    log.critical(f'Unable to format pressure string: "{pressureStr}"')
                    self.pressureRaw = 0

                # Decode the stop switch value
                self.stopswitch = (stopswitchStr == 'S')

                # Decode the foot switch value
                self.footswitch = (footswitchStr == 'F')

                # Latch the foot switch (crude debounce)
                if self.footswitchLatched == False:
                    self.footswitchLatched = self.footswitch

            else:
                log.critical(f'Unable to parse string: {s}')

        else:
            #log.info('Empty read from serial port!')
            pass

        # See if there's a request to send to the arduino
        task, param = self.getRequest()
        if task is not None:

            if task == self.TASKS.PRESSURIZE:
                # Send the valve state to pressurize the bulk
                log.critical('SENDING PRESSURIZE')
                self.ser.write(f'P_'.encode('UTF-8'))

            elif task == self.TASKS.VENT:
                # Send the valve state to de-pressurize the bulk
                log.critical('SENDING DE-PRESSURIZE')
                self.ser.write(f'p_'.encode('UTF-8'))

            elif task == self.TASKS.DISPENSE:
                # Send a dispense down to the filler hardware
                log.critical(f'SENDING DISPENSE FOR {param}ms')
                self.ser.write(f'{param}_'.encode('UTF-8'))

            elif task == self.TASKS.ABORT:
                # Zero out the dispense time to force it to stop
                log.critical('SENDING ABORT')
                self.ser.write(f'0_'.encode('UTF-8'))


    # -------------------------------------------------------------------------
    @property
    def stopping(self):
        return self._stop.isSet()

    def stop(self):
        self._stop.set()

    # -------------------------------------------------------------------------
    def main(self):
        """
        Main thread loop.
        """
        log.debug('Device thread running.')

        hb = 0

        prev = 0
        while not self._stop.wait(self.tickrate):
            try:
                # Run the hardware interface
                self.read()

            except Exception as e:
                log.critical(f'Exception during processing: {e}')
                log.critical(traceback.print_tb(e.__traceback__))

        self.ser.close()

        self.finished.emit()
        log.debug('Device thread stopped.')
