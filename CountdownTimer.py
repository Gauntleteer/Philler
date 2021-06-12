import time
import datetime

class CountdownTimer:
    """
    Define a timer that counts down.  Resolution in seconds.
    """
    def start(self, milliseconds=0, seconds=0, minutes=0, hours=0):
        """
        Start the timer for the provided duration.

        :param duration: Length of timer, in seconds.
        :return: Nothing.
        """
        self.timedelta = datetime.timedelta(milliseconds=milliseconds, seconds=seconds, minutes=minutes, hours=hours)
        self.tstart = self.now
        self.tend = self.tstart + self.timedelta

    def restart(self):
        """
        Restart the timer with the interval used last time.

        :return: Nothing.
        """
        self.tstart = self.now
        self.tend = self.tstart + self.timedelta

    @property
    def now(self): return datetime.datetime.today()

    @property
    def expired(self): return self.now >= self.tend

    def expire(self):
        """
        Expire the timer now.

        :return: Nothing.
        """
        self.tend = self.now