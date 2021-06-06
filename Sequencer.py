# State machine
import logging
from threading import Lock, Event
from transitions import State, Machine
from PyQt5.QtCore import Qt, QSize, QTimer, QObject, QThread, pyqtSignal

# Disable the debug logging from the transitions library
log = logging.getLogger('')
logging.getLogger('transitions').setLevel(logging.WARNING)

class Sequencer(QObject):
    """
    Container class for a generic state machine / sequencer.
    """
    finished = pyqtSignal()
    heartbeat = pyqtSignal(int)

    def __init__(self, *args, **kwargs):

        QObject.__init__(self, *args, **kwargs)

        self.state = None
        self.statemethods = dict()

        # Task properties
        self.tickrate = 0.1
        self._stop = Event()
        self._stop.clear()

    def debug(self, message):
        log.debug(f'{message}')
    def info(self, message):
        log.info(f'{message}')
    def critical(self, message):
        log.critical(f'{message}')

    def prepare(self, states):
        """
        Associate the states with their processing methods.

        :param states: enum of the states that will be used in this model
        :return: Nothing.
        """

        self._states = states
        self.statemethods.clear()

        for state in self._states:
            # Get a method from the class conforming to the name "process_STATE", and associate it with the state enum value
            try:
                self.statemethods[state] = self.__getattribute__(f'process_{state._name_}')
            except AttributeError as e:
                self.critical(f'Model is not fully implemented, missing a process_{state._name_}() method!')
                exit(1)

        # Hook the state transitions to methods in the model
        transitions = [dict(trigger='run', source=x, dest=None, conditions='_procstate') for x in self._states]

        # Create a transitions state machine from our model, enter at the 0th state
        self.machine = Machine(self, states=self._states, transitions=transitions, initial=self._states(0))

    @property
    def terminated(self): return self.state == self._states(len(self._states)-1) # The terminal state is the last in the enum

    @property
    def stateName(self): return self.state.name

    def _procstate(self):
        """
        Generic method called to process the state machine.  Do not call directly.

        :return: T/F on success/fail of the processing.
        """
        old = self.state.name
        self.statemethods[self.state]()
        new = self.state.name
        if old != new:
            self.debug(f'[{old}] -> [{new}]')

        return True

    # --------------
    # Methods for running the sequencer as a task
    @property
    def stopping(self): return self._stop.isSet()

    def stop(self):
        self._stop.set()

    def main(self):
        """
        Main thread loop.
        """
        log.debug('Sequencer thread running.')

        hb = 0

        self.info(f'Sequencer starting.')
        while not self._stop.wait(self.tickrate):

            hb += 1
            self.heartbeat.emit(hb)

            # Run the state machine once
            self.run()

            # End the thread when the sequencer is terminated
            if self.terminated:
                break

        self.finished.emit()

        self.info(f'Sequencer stopped.')




