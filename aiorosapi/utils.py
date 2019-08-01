#
# -+- coding: utf-8 -+-

import logging


class LoggingMixin(object):
    """
    Shortcut for quick logging access
    """
    @property
    def logging(self):
        logger = logging.getLogger(self.__class__.__name__)
        self.__dict__['logging'] = logger
        return logger
