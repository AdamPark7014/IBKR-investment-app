from __future__ import annotations

import logging
from logging import Logger

from pythonjsonlogger import jsonlogger


def setup_logging(level: int = logging.INFO) -> Logger:
    logger = logging.getLogger("ibtrader")
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s %(filename)s %(lineno)d"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger

