#!/usr/bin/python3.5

"""Outlining of the SerialRecorder Class and functionality"""

class DGSRecorder:
    threads = []
    def __init__(self):
        self.read_configuration()
        self.init_logging()
        self.thread_handler()

    def read_configuration(self):
        pass

    def init_logging(self):
        pass


    def _get_avail_serial(self):
        """Return a set of serial port names (e.g. 'ttyS0') on the system"""
        import serial.tools.list_ports 
        ports = {p.name for p in serial.tools.list_ports.comports()}
        return ports

    def _make_thread(port):
        """Called as needed to create a new serial recorder daemon
        performs basic check to ensure port name exists before creating
        the daemonized thread
        """
        if port in self._get_avail_serial():
            thread = dgs.SerialRecorder(port, self.tid)
            self.tid += 1
            thread.start()
            self.threads.append(thread)
            return 1
        return 0

    def thread_handler(self):
        """Create a thread for each available serial port, then
        continue to monitor threads and attempt to restart dead threads
        as needed (e.g. serial port unplugged)
        """
        #Get serial ports registered on system
        for port in self._get_avail_serial():
            #Check if port in thread pool
            if port not in [t.name for t in self.threads]:
                self._make_thread(port)
            #if it is already then continue on

    def run(self):
        """Run the main program loop - checking for thread status and polling
        the system for serial ports - creating a new thread if a new connection
        appears
        """

        ports = self._get_avail_serial()
        while not self.kill:
            n_ports = self._get_avail_serial()
            if n_ports not ports:
                #If the original set doesn't match, get the new members
                diff_ports = n_ports.difference(ports)
                ports = n_ports
                #call the thread handler to create new threads
                self.thread_handler()
            
            for t in self.threads:
                if not t.is_alive():
                    self.threads.remove(t)


            time.sleep(1)
        
        #kill is set
        for t in self.threads:
            t.kill = True
            #t.join()
