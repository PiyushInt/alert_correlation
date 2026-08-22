import json
import logging
import os
import sys
from datetime import datetime
from typing import Any


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
    file_handler = logging.FileHandler("logs/app.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Setup uvicorn loggers to use this format if desired
    logging.getLogger("uvicorn.access").handlers = [stdout_handler]


# Setup on import
setup_logging()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ace.{name}")
