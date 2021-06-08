import sys
import os
import random
import argparse
import coloredlogs, logging
from threading import Lock, Event
from enum import Enum, auto, IntEnum
from queue import Queue, SimpleQueue

from PyQt5 import QtCore, QtWidgets, uic, QtMultimedia
from PyQt5.QtWidgets import QMessageBox, QLabel, QPushButton, QToolButton, QGridLayout
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

# Variables for simulated I/O
simulate = False
simFootSwitchState = False

class PAGES(Enum):
    """
    The pages in the application.
    """
    MAIN = 0  # Start numbering at 0
    DIAG = auto()
    FILL = auto()
    CLEAN= auto()

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

    class STATES(IntEnum):
        """
        The state machine will enter on the 0th state, and when it reaches the final state it will terminate.
        """
        UNINIT                      = 0 # Start numbering at 0

        # Main screens
        STANDBY                     = auto()
        DIAGNOSTICS                 = auto()

        # Bottle filling sequence
        FILL_START1                 = auto()
        FILL_START2                 = auto()
        FILL_START3                 = auto()
        FILL_PRESSURIZE             = auto()
        FILL_PURGE_INIT             = auto()
        FILL_PURGE_SETUP            = auto()
        FILL_PURGE_WAIT             = auto()
        FILL_READY_SETUP            = auto()
        FILL_READY_WAIT             = auto()
        FILL_FILLING                = auto()
        FILL_FILLING_WAIT           = auto()
        FILL_FILLING_RESET          = auto()
        FILL_END                    = auto()
        FILL_TERMINATE              = auto()

        # Cleaning sequence
        CLEAN_START1                = auto()
        CLEAN_START2                = auto()
        CLEAN_START3                = auto()
        CLEAN_PRESSURIZE            = auto()
        CLEAN_READY                 = auto()
        CLEAN_CLEANING              = auto()
        CLEAN_CLEANING_WAIT         = auto()
        CLEAN_END                   = auto()
        CLEAN_TERMINATE             = auto()

        # Failure/terminal states
        FAULT                       = auto()
        TERMINATED                  = auto()

    class BUTTONS(IntEnum):
        """Button inputs from the user"""

        # Common actions
        EXIT                        = 0
        ABORT                       = auto()

        # Simulated actions
        SIM_FOOT_SWITCH             = auto()
        SIM_STOP_SWITCH_OFF         = auto()
        SIM_STOP_SWITCH_ON          = auto()

        # Main screen
        MAIN_ENTER_FILL             = auto()
        MAIN_ENTER_CLEAN            = auto()
        MAIN_ENTER_DIAGNOSTICS      = auto()

        # Fill screen
        FILL_NEXT                   = auto()

        # Clean screen

        # Diagnostics screen

    # The messages that are shown on the progress screen.  Set the second parameter to FALSE to prevent the user from
    # pressing the button to proceed (some other condition will allow proceeding).
    messages = dict({
        STATES.FILL_START1: ('Verify clean drip\n tray installed,\nwith no bottle.\n\n(Tap to continue)', True),
        STATES.FILL_START2: ('Connect filled bulk\ncontainer, air in\nand liquid out.\n\nConnect compressor\nair tubing.\n\nStart compressor.\n\n(Tap to continue)', True),
        STATES.FILL_START3: ('Reset the stop switch.', True),
        STATES.FILL_PRESSURIZE: ('Pressurizing...', False),
        #STATES.FILL_PURGE_INIT: ('', False),
        STATES.FILL_PURGE_SETUP: ('Ready for purging.\n\nPlace waste cup under\nnozzle.\n\nPress foot switch to\npurge tubing, until\nall air is removed.\n\nRemove waste cup.\n\n(Tap to continue)', True),
        STATES.FILL_PURGE_WAIT: ('Purging...', False),
        STATES.FILL_READY_WAIT: ('Ready to fill bottle.\n\nPlace a bottle on\nscale under dispense\nneedle.  Press foot\nswitch once to fill\nbottle.', False),
        #STATES.FILL_FILLING: ('', True),
        STATES.FILL_FILLING_WAIT: ('Filling...', False),
        #STATES.FILL_FILLING_RESET: ('', True),
        #STATES.FILL_END: ('', True),
        #STATES.FILL_TERMINATE: ('', True),
    })


    def __init__(self, filler):
        super(FillingSequencer, self).__init__()

        # Retain a reference to the filler hardware
        self.filler = filler

        # Setup the sequencer with the states we plan to use
        self.prepare(self.STATES)

        # A timer for state timeouts
        self.timer = CountdownTimer()
        self.timer.start(seconds=1)
        self.timer.expire()

        # A queue for requests from the user
        self.requests = SimpleQueue()

    @property
    def message(self):
        """Return the message associated with the current state"""
        try:
            text, enable = self.messages[self.state]
        except KeyError:
            text = ''
            enable = False

        return text, enable

    # -------------------------------------------------------------------------
    def request(self, button):
        """Create request to the state machine based on a button press"""
        self.requests.put(button, block=False)

    def getRequest(self):
        """Get the most recent request"""
        if not self.requests.empty():
            req = self.requests.get(block=False, timeout=0)
        else:
            req = None
        
        return req

    # -------------------------------------------------------------------------
    def requestState(self, newState):
        """Handle the external request to transition to a state"""

        if newState in self.STATES:

            if newState == self.STATES.STANDBY:
                # Going back to standby, turn off anything that might be running
                self.to_STANDBY()

            if newState == self.STATES.DIAGNOSTICS:
                self.to_DIAGNOSTICS()

            if newState == self.STATES.FAULT:
                # Going to fault: turn off anything that might be running
                self.to_FAULT()


            return True, ''

        else:
            return False, 'Invalid state requested!'

    # -------------------------------------------------------------------------
    def process_UNINIT(self):
        """Process any init items here"""
        self.to_STANDBY()

    # -------------------------------------------------------------------------
    def process_STANDBY(self):
        """Transition the user to the various main screens"""
        req = self.getRequest()

        if req in [self.BUTTONS.MAIN_ENTER_FILL]:
            self.to_FILL_START1()
        elif req in [self.BUTTONS.MAIN_ENTER_CLEAN]:
            self.to_CLEAN_START1()
        elif req in [self.BUTTONS.MAIN_ENTER_DIAGNOSTICS]:
            self.to_DIAGNOSTICS()

    # -------------------------------------------------------------------------
    def process_DIAGNOSTICS(self):
        """Run the diagnostics screen, not much to do here, state machine wise"""
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT]:
            self.to_STANDBY()

    # -------------------------------------------------------------------------
    def process_FILL_START1(self):
        """First filling screen page"""
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()
        if req in [self.BUTTONS.FILL_NEXT]:
            self.to_FILL_START2()

    def process_FILL_START2(self):
        """Second filling screen page"""
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()
        if req in [self.BUTTONS.FILL_NEXT]:
            self.to_FILL_START3()

    def process_FILL_START3(self):
        """Wait for the stop switch here"""
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()

        # Wait for the STOP switch state to be ON
        if self.filler.stopswitch:
            self.to_FILL_PRESSURIZE()

        # Or let the simulator dictate the switch
        if simulate and simFootSwitchState:
                self.to_FILL_PRESSURIZE()

    def process_FILL_PRESSURIZE(self):
        req = self.getRequest()

        # Advance to the next state when the pressure is over 30
        if self.filler.pressure >= 30:
            self.to_FILL_PURGE_SETUP()

        # If simulating, disregard the pressure
        if simulate:
            self.to_FILL_PURGE_SETUP()

        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()

    def process_FILL_PURGE_INIT(self):
        """Init the purge state by clearing any previous foot switches"""
        self.filler.footswitch = False
        self.to_FILL_PURGE_SETUP()

    def process_FILL_PURGE_SETUP(self):
        req = self.getRequest()

        # Wait for a footswitch, or use the faked I/O
        if (req in [self.BUTTONS.SIM_FOOT_SWITCH]) or self.filler.footswitch:

            # Acknowledge the foot switch was hit
            self.filler.footswitch = False

            # Send the pulse to do a single purge
            self.filler.request(task=self.filler.TASKS.DISPENSE, param=250)

            # Start a one second timer
            self.timer.start(seconds=1)

            self.to_FILL_PURGE_WAIT()

        # Skip to next screen if user presses the button
        if req in [self.BUTTONS.FILL_NEXT]:
            self.to_FILL_READY_SETUP()

        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()

    def process_FILL_PURGE_WAIT(self):
        """Wait for the purge pulse to complete"""
        if self.timer.expired:
            self.to_FILL_PURGE_SETUP()

        req = self.getRequest()
        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()

    def process_FILL_READY_SETUP(self):
        """Init the state by clearing any previous foot switches"""
        self.filler.footswitch = False
        self.to_FILL_READY_WAIT()

        req = self.getRequest()
        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()

    def process_FILL_READY_WAIT(self):
        """Waiting for user to hit the foot switch to do a fill"""
        req = self.getRequest()

        # Wait for a footswitch, or use the faked I/O
        if (req in [self.BUTTONS.SIM_FOOT_SWITCH]) or self.filler.footswitch:

            # Acknowledge the foot switch was hit
            self.filler.footswitch = False
            self.to_FILL_FILLING()

        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()

    def process_FILL_FILLING(self):
        req = self.getRequest()

        # Send the pulse to do a fill
        self.filler.request(task=self.filler.TASKS.DISPENSE, param=30000)

        # Start a timer
        self.timer.start(seconds=3)

        # Advance to the waiting state
        self.to_FILL_FILLING_WAIT()

        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()

    def process_FILL_FILLING_WAIT(self):
        """Wait for the fill to complete"""

        # Look for timeout
        if self.timer.expired:
            self.to_FILL_READY_WAIT()

        # Is the delivered weight sufficient for a fill?



        req = self.getRequest()

        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()

    def process_FILL_FILLING_RESET(self):
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()

    def process_FILL_END(self):
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT, self.BUTTONS.ABORT]:
            self.to_FILL_TERMINATE()

    def process_FILL_TERMINATE(self):
        log.info('Terminating fill sequence.')

        # Zero out any pulse in progress
        self.filler.request(task=self.filler.TASKS.ABORT)

        # Vent the bulk
        self.filler.request(task=self.filler.TASKS.VENT)

        # Back to first page
        self.to_STANDBY()

    # -------------------------------------------------------------------------
    def process_CLEAN_START1(self):
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT]:
            self.to_CLEAN_TERMINATE()

    def process_CLEAN_START2(self):
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT]:
            self.to_CLEAN_TERMINATE()

    def process_CLEAN_START3(self):
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT]:
            self.to_CLEAN_TERMINATE()

    def process_CLEAN_PRESSURIZE(self):
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT]:
            self.to_CLEAN_TERMINATE()

    def process_CLEAN_READY(self):
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT]:
            self.to_CLEAN_TERMINATE()

    def process_CLEAN_CLEANING(self):
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT]:
            self.to_CLEAN_TERMINATE()

    def process_CLEAN_CLEANING_WAIT(self):
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT]:
            self.to_CLEAN_TERMINATE()

    def process_CLEAN_END(self):
        req = self.getRequest()

        if req in [self.BUTTONS.EXIT]:
            self.to_CLEAN_TERMINATE()

    def process_CLEAN_TERMINATE(self):
        log.info('Terminating cleaning sequence.')
        self.to_STANDBY()

    # -------------------------------------------------------------------------
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

        # Main panel
        sw_pages                  = QtWidgets.QStackedWidget       # type: QtWidgets.QStackedWidget
        b_main_fill_bottles       = QtWidgets.QToolButton          # type: QtWidgets.QToolButton
        b_main_clean_system       = QtWidgets.QToolButton          # type: QtWidgets.QToolButton
        b_main_diagnostics        = QtWidgets.QToolButton          # type: QtWidgets.QToolButton
        b_main_shutdown           = QtWidgets.QToolButton          # type: QtWidgets.QToolButton
        statusbar                 = QtWidgets.QStatusBar           # type: QtWidgets.QStatusBar

        # Fill bottles panel
        b_fill_back               = QtWidgets.QToolButton          # type: QtWidgets.QToolButton
        b_fill_abort              = QtWidgets.QPushButton          # type: QtWidgets.QPushButton
        b_fill_next               = QtWidgets.QToolButton          # type: QtWidgets.QToolButton
        pb_pressure               = QtWidgets.QProgressBar         # type: QtWidgets.QProgressBar

        # Clean system panel
        b_clean_back              = QtWidgets.QToolButton          # type: QtWidgets.QToolButton

        # Diagnostics panel
        l_diag_foot_switch        = QtWidgets.QLabel               # type: QtWidgets.QLabel
        l_diag_stop_switch        = QtWidgets.QLabel               # type: QtWidgets.QLabel
        l_diag_pressure_valve     = QtWidgets.QLabel               # type: QtWidgets.QLabel
        l_diag_pressure_value     = QtWidgets.QLabel               # type: QtWidgets.QLabel
        l_diag_weight_value       = QtWidgets.QLabel               # type: QtWidgets.QLabel
        b_diag_back               = QtWidgets.QToolButton          # type: QtWidgets.QToolButton
        b_diag_sound_test         = QtWidgets.QPushButton          # type: QtWidgets.QPushButton


        #b_go                      = QtWidgets.QPushButton          # type: QtWidgets.QPushButton

        l_weight                  = QtWidgets.QLabel               # type: QtWidgets.QLabel
        l_weight_neg              = QtWidgets.QLabel               # type: QtWidgets.QLabel
        l_weight_g                = QtWidgets.QLabel               # type: QtWidgets.QLabel

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

        # Make the menu bar work the same across all platforms
        self.menubar.setNativeMenuBar(False)

        quit = self.findChild(QtWidgets.QAction, 'actionQuit') # type: QAction
        quit.setShortcut('Ctrl+Q')
        quit.setStatusTip('Quit application')
        quit.triggered.connect(QtWidgets.qApp.quit)

        # Filling device hardware
        self.filler = Filler(simulate=simulate)
        self.fillerThread = QThread()
        self.filler.moveToThread(self.fillerThread)
        self.fillerThread.started.connect(self.filler.main)
        self.filler.finished.connect(self.fillerThread.quit)
        self.filler.finished.connect(self.filler.deleteLater)
        self.fillerThread.finished.connect(self.fillerThread.deleteLater)
        #self.hw.progress.connect(self.reportProgress)
        self.filler.changed.connect(self.fillerChanged)

        # Filling device state machine
        self.seq = FillingSequencer(filler=self.filler)
        self.seqThread = QThread()
        self.seq.moveToThread(self.seqThread)
        self.seqThread.started.connect(self.seq.main)
        self.seq.finished.connect(self.seqThread.quit)
        self.seq.finished.connect(self.seq.deleteLater)
        self.seqThread.finished.connect(self.seqThread.deleteLater)

        self.w.b_main_shutdown.clicked.connect(QtWidgets.qApp.quit)

        # Start the threads
        self.fillerThread.start()
        self.seqThread.start()

        # Define timers to periodically update screen widgets
        self.statusTimer = QTimer()
        self.statusTimer.timeout.connect(self.updateStatus)
        self.statusTimer.start(100)


        self.stateTimer = QTimer()
        self.stateTimer.timeout.connect(self.updateState)
        self.stateTimer.start(100)





        # Start out on the main page
        self.w.sw_pages.setCurrentIndex(0)
        self.selectPanel(PAGES.MAIN)




        # Add a state name to the status bar
        self.l_state = QtWidgets.QLabel()
        self.l_state.setText(self.seq.stateName)
        self.w.statusbar.addPermanentWidget(self.l_state, stretch=1)

        self.l_message = QtWidgets.QLabel()
        self.l_message.setText('')
        self.w.statusbar.addPermanentWidget(self.l_message, stretch=1)

        # Create the simulated I/O, but only add it to the form if enabled
        self.b_foot_switch_simulate = QtWidgets.QPushButton('FOOT')
        self.b_stop_switch_simulate = QtWidgets.QPushButton('STOP')
        if simulate:
            self.w.statusbar.addPermanentWidget(self.b_foot_switch_simulate, stretch=1)
            self.w.statusbar.addPermanentWidget(self.b_stop_switch_simulate, stretch=1)
            self.b_foot_switch_simulate.clicked.connect(self.buttonClicked)
            self.b_stop_switch_simulate.clicked.connect(self.buttonClicked)

        # Add a connection status light to the status bar
        self.l_connected = QtWidgets.QLabel()
        self.l_connected.setText('TEXT')
        self.l_connected.setStyleSheet('color: red')
        self.w.statusbar.addPermanentWidget(self.l_connected)

        # Hook the buttons to their processing logic
        for button in [
            # Main panel
            self.w.b_main_fill_bottles, self.w.b_main_clean_system,
            # Fill panel
            self.w.b_fill_back, self.w.b_fill_next, self.w.b_fill_abort,
            # Clean panel
            self.w.b_clean_back,
            # Diagnostics panel
            self.w.b_main_diagnostics, self.w.b_diag_back, self.w.b_diag_sound_test]:

            button.clicked.connect(self.buttonClicked)


    def selectPanel(self, panel):
        """Select one of the stacked main panels"""
        self.w.sw_pages.setCurrentIndex(panel.value)

    def updateStatus(self):
        """Update the widgets on the status pane"""
        self.l_state.setText('  STATE: ' + self.seq.stateName)
        self.l_message.setText('')

        if self.filler.connected:
            self.l_connected.setText('CONNECTED')
            self.l_connected.setStyleSheet('color: green')

        else:
            self.l_connected.setText('DISCONNECTED')
            self.l_connected.setStyleSheet('color: red')

        #def fillerChanged(self):
        """Update the widgets that display values from the filler device"""
        weight_val = self.filler.weight
        pressure_val = self.filler.pressure

        # Diagnostics page
        self.w.l_diag_weight_value.setText(f'{weight_val:03.2f} g')
        self.w.l_diag_pressure_value.setText(f'{pressure_val:03.2f} psi')

        # Fill bottles page
        if weight_val > 0:
            self.w.l_weight_neg.setText('')

        self.w.l_weight.setText(f'{abs(weight_val):03.2f}')

        self.w.pb_pressure.setValue(round(pressure_val))



    def play(self):
        x = random.random()

        if x > 0.5:
            QtMultimedia.QSound.play('bell.wav')
        else:
            QtMultimedia.QSound.play('agogo.wav')


    def updateState(self):
        """Update the screen to match the state machine"""
        states = self.seq.STATES
        fillStates = [state for state in range(states.FILL_START1, states.FILL_TERMINATE)]
        cleanStates = [state for state in range(states.CLEAN_START1, states.CLEAN_TERMINATE)]

        # Set the right panel
        if self.seq.state in [states.STANDBY, states.FAULT, states.TERMINATED]:
            self.selectPanel(PAGES.MAIN)

        elif self.seq.state in [states.DIAGNOSTICS]:
            self.selectPanel(PAGES.DIAG)

        elif self.seq.state in fillStates:
            self.selectPanel(PAGES.FILL)
            message, enable = self.seq.message
            self.w.b_fill_next.setText(message)
            self.w.b_fill_next.setEnabled(enable)

        elif self.seq.state in cleanStates:
            self.selectPanel(PAGES.CLEAN)


    def buttonClicked(self):
        """Handle buttons being clicked"""
        global simFootSwitchState

        success = True
        message = ''

        buttons = self.seq.BUTTONS

        # Which button originated the click?
        origin = self.sender()

        # Fill related buttons
        if origin == self.w.b_main_fill_bottles:
            self.seq.request(buttons.MAIN_ENTER_FILL)

        elif origin == self.w.b_fill_back:
            self.seq.request(buttons.EXIT)

        elif origin == self.w.b_fill_next:
            self.seq.request(buttons.FILL_NEXT)

        elif origin == self.w.b_fill_abort:
            self.seq.request(buttons.ABORT)

        # Clean related buttons
        elif origin == self.w.b_main_clean_system:
            self.seq.request(buttons.MAIN_ENTER_CLEAN)

        elif origin == self.w.b_clean_back:
            self.seq.request(buttons.EXIT)

        # Diagnostics related buttons
        elif origin == self.w.b_main_diagnostics:
            self.seq.request(buttons.MAIN_ENTER_DIAGNOSTICS)

        elif origin == self.w.b_diag_back:
            self.seq.request(buttons.EXIT)


        # Simulated I/O buttons
        elif origin == self.b_foot_switch_simulate:
            self.seq.request(buttons.SIM_FOOT_SWITCH)

        elif origin == self.b_stop_switch_simulate:

            # Invert the switch state
            simFootSwitchState = not simFootSwitchState

            if simFootSwitchState:
                self.seq.request(buttons.SIM_STOP_SWITCH_ON)
                self.b_stop_switch_simulate.setStyleSheet('background-color: blue')
            else:
                self.seq.request(buttons.SIM_STOP_SWITCH_OFF)
                self.b_stop_switch_simulate.setStyleSheet('')



        # Display the failure text
        if not success:
            self.l_message.setText(message)



# end of class MainWindow


if __name__ == '__main__':

    # -------------------------------------------------------------------------
    # Commandline arguments
    parser = argparse.ArgumentParser(description='Philler')
    #parser.add_argument('-d', '--debug', help='Enable debugging output', action='store_true')
    parser.add_argument('-s', '--simulate', help='Enable simulation of I/O', action='store_true')
    args = parser.parse_args()

    # Get the debug argument first, as it drives our logging choices
    #if args.debug:
    #    debug = True

    if args.simulate:
        log.critical('SIMULATING I/O')
        simulate = True



    # GUI
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    app.exec_()




