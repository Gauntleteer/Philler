# State machine
import logging
import serial
from threading import Lock, Event
from PyQt5.QtCore import Qt, QSize, QTimer, QObject, QThread, pyqtSignal

log = logging.getLogger('')

class Filler(QObject):

    finished = pyqtSignal()
    heartbeat = pyqtSignal(int)

    def __init__(self, *args, **kwargs):

        QObject.__init__(self, *args, **kwargs)

        # Task properties
        self.tickrate = 0.1
        self._stop = Event()
        self._stop.clear()

    def ioDriver(self):
        log.debug('pass')


    @property
    def stopping(self):
        return self._stop.isSet()

    def stop(self):
        self._stop.set()

    def baz(self):
        #ser.write(b'*IDN?\n')
        # ser.write(b'ERR?\n')
        pass

    def run(self):
        """
        Main thread loop.
        """
        hb = 0
        ser = serial.Serial('/dev/ttyUSB0', 19200, timeout=0.5)

        log.debug('Device thread running.')
        while not self._stop.wait(self.tickrate):

            hb += 1
            self.heartbeat.emit(hb)

            try:
                # Run the hardware interface
                #self.ioDriver()

                #s = ser.read(100)
                s = ser.read_until('\n')
                log.debug(s)


            except Exception as e:
                log.critical(f'Exception during processing: {e}')
                log.critical(traceback.print_tb(e.__traceback__))

        ser.close()

        self.finished.emit()
        log.debug('Device thread stopped.')
