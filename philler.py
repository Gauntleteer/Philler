import sys
import os
import argparse
import traceback
import coloredlogs, logging
from threading import Lock, Event
import serial


from PyQt5 import QtCore, QtWidgets, uic
from PyQt5.QtWidgets import QMessageBox, QLabel, QPushButton, QToolButton, QCheckBox, QFileDialog, QTableWidgetItem, QStyledItemDelegate
from PyQt5.QtCore import Qt, QSize, QTimer, QObject, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QPen, QColor, QImage, QPixmap


# -------------------------------------------------------------------------
# Set up the base logger
coloredlogs.DEFAULT_LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
coloredlogs.DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S.%f'
coloredlogs.install(level='DEBUG')
log = logging.getLogger('')

# Disable the debug logging from Qt
logging.getLogger('PyQt5').setLevel(logging.WARNING)


def showDialog(text, yes=False, cancel=False):
    """
    Show a message box to the user.

    :param text: The message to be displayed.
    :param yes: Use "Yes/No" instead of "OK/Cancel"
    :param cancel: Show a Cancel button, versus just OK.
    :return: Nothing.
    """

    # Create a message box
    msgbox = QtWidgets.QMessageBox()
    msgbox.setIcon(QMessageBox.Information)
    msgbox.setText(text)
    msgbox.setWindowTitle('Message')

    # Add buttons, either OK or OK+Cancel or Yes+No
    if yes:
        msgbox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    elif cancel:
        msgbox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    else:
        msgbox.setStandardButtons(QMessageBox.Ok)

    # Test the return from the message box
    returnvalue = msgbox.exec()
    if returnvalue in [QMessageBox.Ok, QMessageBox.Yes]:
        return True
    else:
        return False



class FillingHardware(QObject):

    finished = pyqtSignal()
    progress = pyqtSignal(int)

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
        i = 0
        ser = serial.Serial('/dev/ttyUSB0', 19200, timeout=0.5)

        log.debug('Device thread running.')
        while not self._stop.wait(self.tickrate):

            i += 1
            self.progress.emit(i)

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





class MainWindow(QtWidgets.QMainWindow):

    class RefWidgets:
        """
        Container class for the widgets on the form that has stronger typing for use in IDEs.
        """

        # Define each widget here by name with an instance of it that will be replaced at runtime.
        # The extra "type:" indicator is for PyCharm only, since the declaration is a type and
        # not an instance.

        # Name                      Type (for locating)         Type (forced for PyCharm type hinting only)
        b_go                      = QtWidgets.QPushButton          # type: QtWidgets.QPushButton


        def __init__(self, form):
            """
            Iterate all the widgets in this class and find their actual instances in the form.

            :param form: An instance of a form with the desired widgets instantiated in it.
            :return: Nothing.
            """

            for name in dir(self):

                # Skip the entities that aren't the desired widgets
                if name.startswith('__'):
                    continue

                # Skip the methods
                if name == 'add':
                    continue

                # Find the widget on the form by name and type
                wtype = self.__getattribute__(name)
                widget = form.findChild(wtype, name)

                # Bail out if we can't find one!
                if widget is None:
                    print(f'Cannot locate widget {name} of type {wtype} in UI file!')
                    exit(1)

                # Reassign the widget in this instance to the one on the form
                self.__setattr__(name, widget)

        def add(self, name, widget):
            """
            Add a widget to the catalog.

            :param widget: A widget instance.
            :param name: The widget name to reference it with.
            :return: Nothing.
            """
            self.__setattr__(name, widget)



    # -----------------------------------------------------------------------------
    def __init__(self, *args, **kwargs):

        self.popups = {}
        self.template = None

        # Make access to data be thread safe with a mutex (chart data, in particular)
        self._mutex = QtCore.QMutex()

        QtWidgets.QMainWindow.__init__(self, *args, **kwargs)

        # Load the UI file
        filename = 'Philler_Main.ui'
        uic.loadUi(filename, self)

        # Find the widgets
        self.w = self.RefWidgets(self)

        self.setupUi()
        self.show()

    # -----------------------------------------------------------------------------
    def setupUi(self):

        title = 'Philler'
        self.setWindowTitle(title)

        # -----------------------------------------------------------------------------
        # Pull down menu

        # Make the menu bar work the same across all platforms (looking at you, MacOS)
        self.menubar.setNativeMenuBar(False)

        quit = self.findChild(QtWidgets.QAction, 'actionQuit') # type: QAction
        quit.setShortcut('Ctrl+Q')
        quit.setStatusTip('Quit application')
        quit.triggered.connect(QtWidgets.qApp.quit)

        self.w.b_go.pressed.connect(self.goPressed)




        self.thread = QThread()

        # Filling device hardware
        self.hw = FillingHardware()

        # Move worker to the thread
        self.hw.moveToThread(self.thread)

        # Connect signals and slots
        self.thread.started.connect(self.hw.run)
        self.hw.finished.connect(self.thread.quit)
        self.hw.finished.connect(self.hw.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        #self.hw.progress.connect(self.reportProgress)

        # Start the thread
        self.thread.start()


    def goPressed(self):
        showDialog('GO!')




# end of class MainWindow









if __name__ == '__main__':

    # GUI
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    app.exec_()




