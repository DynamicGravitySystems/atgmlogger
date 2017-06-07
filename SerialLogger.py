import os
import sys
import argparse
import yaml
import logging
import logging.config
import threading
import pkg_resources


class SerialLogger:
    def __init__(self, argv):
        parser = argparse.ArgumentParser(prog=argv[0],
                                         description="Serial Data Logger")
        parser.add_argument('-V', '--version', action='version',
                            version='0.1')
        parser.add_argument('-v', '--verbose', action='count')
        parser.add_argument('-l', '--logdir', action='store', default='/var/log/dgs')
        opts = parser.parse_args(argv[1:])

        self.logdir = os.path.abspath(opts.logdir)
        self.logname = __name__
        self.verbosity = opts.verbose
        self.init_logging()

        # Thread signal definitions
        self.exit_signal = threading.Event()
        self.data_signal = threading.Event()
        self.usb_signal = threading.Event()

    def init_logging(self):
        """
        Initialize logging facilities, defined in logging.yaml file.
        :return:
        """
        config_f = 'logging.yaml'
        log_resource = pkg_resources.resource_stream(__package__, config_f)
        log_dict = yaml.load(log_resource)

        # Apply base logdir to any filepaths in log_dict
        for hdlr, properties in log_dict.get('handlers').items():
            path = properties.get('filename', False)
            if path:
                # Rewrite log config path with self.logdir as the base
                _, fname = os.path.split(path)
                abs_path = os.path.join(self.logdir, fname)
                log_dict['handlers'][hdlr]['filename'] = abs_path

        # Check/create logging directory
        if not os.path.exists(self.logdir):
            os.makedirs(self.logdir, mode=0o755, exist_ok=False)

        logging.config.dictConfig(log_dict)
        # Select only the first logger defined in the log yaml
        self.logname = list(log_dict.get('loggers').keys())[0]

    def run(self):
        pass


if __name__ == "__main__":
    main = SerialLogger(sys.argv)
    main.run()
