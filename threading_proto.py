#!/usr/bin/python3.5
import threading
import logging
import time
import sys

class TestThread(threading.Thread):
    def __init__(self, name, runtime=5, interval=1):
        threading.Thread.__init__(self)
        self.name = name
        self.runtime = runtime
        self.interval = interval
        self.count = 0
        self.log = logging.getLogger('thread.{}'.format(self.name))
        self.log.setLevel(logging.DEBUG)
        fmtr = logging.Formatter('%(asctime)s - %(name)s - %(message)s', datefmt='%H:%M:%S')
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmtr)
        if not self.log.hasHandlers():
            self.log.addHandler(sh)

        
    def run(self):
        self.log.info('Spawning new thread: {}'.format(self.name))
        while self.runtime > 0:
            #self.log.debug('running iteration on thread {}'.format(self.name))
            self.runtime -= 1
            self.count += 1
            time.sleep(self.interval)
        self.log.debug('exiting thread {} after {} iterations'.format(self.name, self.count))

class ThreadRunner:
    def __init__(self):
        self.log = logging.getLogger('threadRunner')
        self.log.setLevel(logging.DEBUG)
        sh = logging.StreamHandler(sys.stdout)
        self.log.addHandler(sh)
        self.ports = ['tty0', 'tty1', 'ttyS0']
        self.threads = []
        self.runcount = 0

    def thread_handler(self):
        for port in self.ports:
            if port not in [t.name for t in self.threads]:
                self.log.debug('thread_handler creating new thread {}'.format(port))
                self.make_thread(port)

    def make_thread(self, port):
        thread = TestThread(port)
        thread.start()
        self.threads.append(thread)

    def run(self):
        self.log.debug("initiating")
        while True:
            self.log.debug("Main run iter {}".format(self.runcount))
            if self.runcount == 3:
                self.ports.append('ttyUSB1')
                self.log.debug("new port ttyUSB1 added")
            if self.runcount == 5:
                self.ports.remove('tty0')
                self.log.debug("port tty0 no longer available")
            for thread in self.threads[:]:
                if not thread.isAlive():
                    self.log.debug("thread {} is dead".format(thread.name))
                    self.threads.remove(thread)
                    self.thread_handler()
            self.thread_handler()
            self.runcount += 1
            time.sleep(1)


if __name__ == "__main__":
    unit = ThreadRunner()
    unit.run()
