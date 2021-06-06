import time
import logging
import serial
import traceback
from threading import Lock, Event
from queue import Queue
import re

from PyQt5.QtCore import Qt, QSize, QTimer, QObject, QThread, pyqtSignal

log = logging.getLogger('')
#logging.getLogger('serial').setLevel(logging.WARNING)


class Filler(QObject):

    finished = pyqtSignal()
    heartbeat = pyqtSignal(int)
    changed = pyqtSignal()

    def __init__(self, *args, **kwargs):

        QObject.__init__(self, *args, **kwargs)

        # Conversion factors
        self.PSIperCount = None
        self.PSIintercept = None

        # Serial interface
        self.ser = None
        self.port = '/dev/ttyUSB0'
        self.baudrate = 19200
        self.lastmessage = 0

        # Interface to callers
        self._commands = Queue()
        self._weight = 0.0
        self._stable = False
        self._stopswitch = False
        self._footswitch = False
        self.pressureRaw = 0

        # Task properties
        self.tickrate = 0.1
        self._stop = Event()
        self._stop.clear()
        self.lock = Lock()


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

    @property
    def connected(self):
        # If we have received a message in the last second, we are "connected"
        now = time.time()
        return (now - self.lastmessage < 1)

    @property
    def weight(self):
        with self.lock: return self._weight
    @weight.setter
    def weight(self, val):
        with self.lock: self._weight = val

    @property
    def stable(self):
        with self.lock: return self._stable
    @stable.setter
    def stable(self, val):
        with self.lock: self._stable = val

    @property
    def footswitch(self):
        with self.lock: return self._footswitch
    @footswitch.setter
    def footswitch(self, val):
        with self.lock: self._footswitch = val

    @property
    def stopswitch(self):
        with self.lock: return self._stopswitch
    @stopswitch.setter
    def stopswitch(self, val):
        with self.lock: self._stopswitch = val

    @property
    def pressure(self):
        # Convert the raw pressure value into PSI
        with self.lock:
            p = self.pressureRaw

            # Clip the pressure at minimum/maximum
            if p > 1023:
                p = 1023
            if p < 0:
                p = 0

            return self.countsToPSI(p)


    def setup(self, port, baudrate):
        """Set the properties of the serial port"""
        self.port = port
        self.baudrate = baudrate


    def read(self):
        """Read from the serial port and parse the fields out"""
        if self.ser is None:
            try:
                self.ser = serial.Serial(self.port, self.baudrate, timeout=0.05)
            except serial.SerialException:
                return

        # Read a line from the Arduino
        #s = self.ser.read_until('\r\n')
        s = self.ser.readline()
        #log.debug(s)

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

                # Decode the stop switch value
                self.footswitch = (footswitchStr == 'F')

                self.changed.emit()

            else:
                log.critical(f'Unable to parse string: {s}')

        else:
            #log.info('Empty read from serial port!')
            pass

    @property
    def stopping(self):
        return self._stop.isSet()

    def stop(self):
        self._stop.set()

    def baz(self):
        #ser.write(b'*IDN?\n')
        # ser.write(b'ERR?\n')
        pass

    def main(self):
        """
        Main thread loop.
        """
        log.debug('Device thread running.')

        hb = 0

        prev = 0
        while not self._stop.wait(self.tickrate):

            now = time.time()
            elapsed = now - prev
            prev = now
            #log.info(f'Elapsed: {elapsed}')

            hb += 1
            self.heartbeat.emit(hb)

            try:
                # Run the hardware interface
                self.read()

                #s = ser.read(100)
                #s = ser.read_until('\n')
                #log.debug(s)

            except Exception as e:
                log.critical(f'Exception during processing: {e}')
                log.critical(traceback.print_tb(e.__traceback__))

        self.ser.close()

        self.finished.emit()
        log.debug('Device thread stopped.')
