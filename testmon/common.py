import logging


def dummy():
    pass


def get_logger(name):
    logging.basicConfig(format="%(levelname)s: %(message)s.", level=logging.WARNING)
    return logging.getLogger(name)
