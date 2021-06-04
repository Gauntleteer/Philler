import sys
import os
import argparse
import traceback
import coloredlogs, logging
from threading import Lock, Event
from enum import Enum, auto

from PyQt5 import QtCore, QtWidgets, uic
from PyQt5.QtWidgets import QMessageBox, QLabel, QPushButton, QToolButton, QCheckBox, QFileDialog, QTableWidgetItem, QStyledItemDelegate
from PyQt5.QtCore import Qt, QSize, QTimer, QObject, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QPen, QColor, QImage, QPixmap

from Hardware import Filler
from Sequencer import Sequencer
from CountdownTimer import CountdownTimer

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


class FillingSequencer(Sequencer):

    class STATES(Enum):
        """
        The state machine will enter on the 0th state, and when it reaches the final state it will terminate.
        """
        UNINIT       = 0 # Start numbering at 0
        STANDBY      = auto()
        IDLE         = auto()
        FAULT        = auto()
        TERMINATED   = auto()

    def __init__(self):
        super(FillingSequencer, self).__init__()

        # Setup the sequencer with the states we plan to use
        self.prepare(self.STATES)

        # A timer for connect timeouts
        self.connecttimer = CountdownTimer()
        self.connecttimer.start(minutes=1)
        self.connecttimer.expire()

    def process_UNINIT(self):
        # Clear any start request
        #self.seqrequest = ''

        self.to_STANDBY()

    def process_STANDBY(self):
        self.to_IDLE()

    def process_IDLE(self):
        pass

    def process_FAULT(self):
        pass

    def process_TERMINATED(self):
        pass




class MainWindow(QtWidgets.QMainWindow):

    class RefWidgets:
        """
        Container class for the widgets on the form that has stronger typing for use in IDEs.
        """

        # Define each widget here by name with an instance of it that will be replaced at runtime.
        # The extra "type:" indicator is for PyCharm only, since the declaration is a type and
        # not an instance.

        # Name                      Type (for locating)              Type (forced for PyCharm type hinting only)
        b_go                      = QtWidgets.QPushButton          # type: QtWidgets.QPushButton
        l_weight                  = QtWidgets.QLabel               # type: QtWidgets.QLabel
        l_weight_neg              = QtWidgets.QLabel               # type: QtWidgets.QLabel
        l_weight_g                = QtWidgets.QLabel               # type: QtWidgets.QLabel
        b_shutdown                = QtWidgets.QPushButton          # type: QtWidgets.QPushButton

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
        #self.show()
        self.showFullScreen()

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

        # Filling device hardware
        self.filler = Filler()
        self.fillerThread = QThread()
        self.filler.moveToThread(self.fillerThread)
        self.fillerThread.started.connect(self.filler.main)
        self.filler.finished.connect(self.fillerThread.quit)
        self.filler.finished.connect(self.filler.deleteLater)
        self.fillerThread.finished.connect(self.fillerThread.deleteLater)
        #self.hw.progress.connect(self.reportProgress)
        self.filler.changed.connect(self.onUpdate)

        # Filling device hardware
        self.seq = FillingSequencer()
        self.seqThread = QThread()
        self.seq.moveToThread(self.seqThread)
        self.seqThread.started.connect(self.seq.main)
        self.seq.finished.connect(self.seqThread.quit)
        self.seq.finished.connect(self.seq.deleteLater)
        self.seqThread.finished.connect(self.seqThread.deleteLater)

        self.w.b_shutdown.clicked.connect(QtWidgets.qApp.quit)

        # Start the threads
        self.fillerThread.start()
        self.seqThread.start()




    def goPressed(self):
        showDialog('GO!')

    def onUpdate(self):
        val = self.filler.weight
        if val > 0:
            self.w.l_weight_neg.setText('')

        self.w.l_weight.setText(f'{abs(val):03.2f}')






# end of class MainWindow









if __name__ == '__main__':

    # GUI
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    app.exec_()




