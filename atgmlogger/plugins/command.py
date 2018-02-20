# -*- coding: utf-8 -*-

import queue

from atgmlogger import APPLOG
from atgmlogger.dispatcher import PluginInterface

# TODO: I don't think this is really necessary any more


class Command:
    # TODO: Add on_complete hook? allow firing of lambda on success
    """
    Command class which encapsulates a function and its arguments, to be
    executed by the CommandListener subscriber.

    Commands may be assigned an int priority where 0 is the highest priority.
    This class implements the necessary interface to be compatible with the
    PriorityQueue. e.g.:
        Command[0] returns the priority
        Command < OtherCommand returns True if Command.priority <
        OtherCommand.priority

    The result of the executed function is returned via the execute or call
    methods to be captured if necessary.

    """
    def __init__(self, command, *cmd_args, priority=None, name=None, log=True,
                 **cmd_kwargs):
        self.priority = priority or 9
        self.functor = command
        self.name = name or command.__name__
        self._log = True
        self._args = cmd_args
        self._kwargs = cmd_kwargs

    def execute(self):
        res = self.functor(*self._args, **self._kwargs)
        if self._log:
            APPLOG.info("Command {name} executed with result: {result}"
                        .format(name=self.name, result=res))
        return res

    def __getitem__(self, item):
        if item == 0:
            return self.priority
        raise IndexError

    def __lt__(self, other):
        return self.priority < other.priority


class CommandListener(PluginInterface):
    consumerType = Command

    def __init__(self):
        super().__init__()
        self._results = []

    def run(self):
        while not self.exiting:
            try:
                cmd = self.get(block=True, timeout=1)
            except queue.Empty:
                continue
            result = cmd.execute()
            self._results.append(result)
            APPLOG.debug("Command executed without exception.")
            self.queue.task_done()

        APPLOG.debug("Exiting %s thread.", self.__class__.__name__)

    def configure(self, **options):
        super().configure(**options)
