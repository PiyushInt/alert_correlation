import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any

from ace.config import settings


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        return json.dumps(log_data)


def setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger("ace")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = JSONFormatter()

    # Stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    # File handler
    file_handler = RotatingFileHandler(
        "logs/app.log", maxBytes=settings.LOG_MAX_BYTES, backupCount=settings.LOG_BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Setup uvicorn loggers to use this format if desired
    logging.getLogger("uvicorn.access").handlers = [stdout_handler]


# Setup on import is removed to avoid redundant execution when module is imported


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ace.{name}")
