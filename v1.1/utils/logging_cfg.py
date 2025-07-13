import logging
import sys

def setup_logger(name: str, level: str = "INFO"):
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger
