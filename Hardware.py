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

        # Serial interface
        self.ser = None
        self.port = '/dev/ttyUSB0'
        self.baudrate = 19200
        self.connected = False

        # Interface to callers
        self._commands = Queue()
        self._weight = 0.0
        self._stable = False
        self._stopswitch = False
        self._footswitch = False
        self._pressure = 0.0

        # Task properties
        self.tickrate = 0.1
        self._stop = Event()
        self._stop.clear()
        self.lock = Lock()

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
        with self.lock: return self._pressure
    @pressure.setter
    def pressure(self, val):
        with self.lock: self._pressure = val

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

            # Data Format example:  "+    0.00g  ;194;s;f"
            match = re.match('([-+ ]*)\s*(\d+\.\d+)g\s*;(\d+);([sS]);([fF])', s.decode('UTF-8'))
            if match:
                posneg = match.groups()[0].strip()
                weight = match.groups()[1]
                pressure = match.groups()[2]
                stopswitch = match.groups()[3]
                footswitch = match.groups()[4]

                try:
                    weightStr = posneg + weight
                    p = float(weightStr)
                    self.weight = p
                    #log.debug(f'Weight: {p}')

                    self.connected = True
                    self.changed.emit()
                except ValueError as e:
                    log.critical(f'Unable to format weight string: {weightStr}')
                    self.weight = -99.99
            else:
                log.critical(f'Unable to parse string: {s}')

        else:
            #log.info('Empty read from serial port!')
            self.connected = False

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
