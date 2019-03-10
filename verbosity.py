import argparse
import logging


# Custome logfilter for selective debug messages
class blacklistLogFilter(logging.Filter):
    def __init__(self, funclist):
        ''' funclist is a list of function names to exclude'''
        self.funclist = funclist

    def filter(self, rec):
        return rec.funcName not in self.funclist


# Custome logfilter for selective debug messages
class whitelistLogFilter(logging.Filter):
    def __init__(self, funclist, verbosity):
        ''' funclist is a list of function names to include in the output '''

        '''
        DEBUG level already set for records  coming in, filter down to the
        specified verbosity except for those on the whitelist
        '''
        self.funclist = funclist
        self.verbosity = verbosity

    def filter(self, rec):
        # Immediately allow record if it's in the whitelist
        return rec.funcName in self.funclist
        # Loglevels for verbosity 1,2,3
        minloglevels = [20, 10, 10]
        # return true if record level >= verbosity
        return(rec.level >= minloglevels[verbosity])


def initialize(logger):
    """ Initialize pylogging and add handler to roothandler """
    # clear existing handlers (pythonista)
    rootlogger = logging.getLogger()
    rootlogger.handlers = []
    logger.handlers = []

    logFormatter = logging.Formatter(
        '%(asctime)s [%(filename)s] [%(funcName)s] [%(levelname)s] ' +
        '[%(lineno)d] %(message)s')

    # configure stream handler (this is what prints to the console)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootlogger.addHandler(consoleHandler)


def add_arguments(parser):
    parser.add_argument('-v', '--verbosity', action='count',
                        help='increase output verbosity: '
                        'INFO, DEBUG, DEEPDEBUG', default=0)
    mgroup = parser.add_mutually_exclusive_group()
    mgroup.add_argument('-vbl', '--vblacklist', nargs='+',
                        help='Blacklist of modules and functions to ignore '
                        'when logging')
    mgroup.add_argument('-vwl', '--vwhitelist', nargs='+',
                        help='Whitelist of modules and functions to include '
                        'when logging')


def handle_arguments(args, logger):
    """ process the logging arguments and set the appropriate logger levels """

    '''
    -v = INFO on top (non-root) logger
    -vv = DEBUG on top (non-root) logger
    -vvv = DEBUG on the root logger

    -vbl = set the specified level but filter out the specified modules or
        functionnames

    -vwl = output logs of the specified level, but always show debug code for
        the specified modules of functions.  Note: This makes no sense when
        -vvv.

    Set log level and configure log formatter

    Logging Basics:
        * Loggers: expose the interface that application code directly uses.
        * Filters: provide a finer grained facility for determining which log
    records to send to the handlers
            ** Filters can be placed on Loggers and on Handlers
        * Handlers: send log records (created by loggers) to the appropriate
    destination.

        * Formatters:  specify the layout of log records in the final output.
    '''
    rootlogger = logging.getLogger()

    # Check to see if no black/whitelist or if using -vvv and whitelist
    #   which has no effect as -vvv supersedes
    if (not(args.vblacklist or args.vwhitelist) or
            (args.vwhitelist and args.verbosity == 3)):
        if args.verbosity == 1:
            logger.setLevel(logging.INFO)
        elif args.verbosity == 2:
            logger.setLevel(logging.DEBUG)
        elif args.verbosity == 3:
            rootlogger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.WARNING)
    else:
        # Set up filter if debug was chosen - to do this we set debug and
        # then use filters to filter in or out the messages

        # If there is a whitelist, turn on full debugging - then use a filter
        # to select the appropriate records
        if args.vwhitelist:
            rootlogger.setLevel(logging.DEBUG)

            # Get the current rootlogger Streamhandler and add a filter to it
            for handler in rootlogger.handlers:
                if isinstance(handler, logging.StreamHandler):
                    handler.addFilter(whitelistLogFilter(
                        args.vwhitelist, args.verbosity))
        else:
            # vblacklist
            for handler in rootlogger.handlers:
                if isinstance(handler, logging.StreamHandler):
                    handler.addFilter(blacklistLogFilter(
                        args.vblacklist))
            if args.verbosity == 3:
                rootlogger.setLevel(logging.DEBUG)
            elif args.verbosity == 2:
                logger.setLevel(logging.DEBUG)
            else:
                logger.setLevel(logging.INFO)
