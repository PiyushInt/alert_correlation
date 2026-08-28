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

    # Determine process name based on sys.argv
    argv_str = " ".join(sys.argv).lower()
    if "uvicorn" in argv_str or "main.py" in argv_str:
        base_name = "app-api"
    elif "ingest_worker" in argv_str:
        base_name = "app-ingest-worker"
    elif "correlation_worker" in argv_str:
        base_name = "app-correlation-worker"
    elif "pytest" in argv_str:
        base_name = "app-test"
    elif "runner" in argv_str:
        base_name = "app-eval-runner"
    else:
        # Fallback without bare app.log to prevent shared inode defect
        script_name = os.path.basename(sys.argv[0])
        base_name = (
            f"app-{script_name.replace('.py', '')}"
            if script_name and script_name != "-c"
            else "app-unknown"
        )

    current_pid = os.getpid()
    log_filename = f"logs/{base_name}-{current_pid}.log"

    # Cleanup dead PID logs to prevent unbounded accumulation
    import glob
    import subprocess

    for existing_log in glob.glob(f"logs/{base_name}-*.log*"):
        try:
            # Extract PID from string like logs/app-api-12345.log or logs/app-api-12345.log.1
            parts = existing_log.split("-")
            if len(parts) >= 3:
                pid_part = parts[-1].split(".")[0]
                if pid_part.isdigit():
                    pid = int(pid_part)
                    if pid != current_pid:
                        try:
                            # Use ps to ensure the PID hasn't been recycled by an unrelated process
                            result = subprocess.run(
                                ["ps", "-p", str(pid), "-o", "command="],
                                capture_output=True,
                                text=True,
                                check=True,
                            )
                            command = result.stdout.lower()
                            # If command has ACE/python/pytest/uvicorn, it's alive.
                            if not any(
                                marker in command
                                for marker in ["python", "uvicorn", "pytest", "ace"]
                            ):
                                os.remove(existing_log)
                        except subprocess.CalledProcessError:
                            # Process is dead, cleanup file
                            os.remove(existing_log)
                        except OSError:
                            pass
        except Exception:
            pass

    # File handler
    file_handler = RotatingFileHandler(
        log_filename, maxBytes=settings.LOG_MAX_BYTES, backupCount=settings.LOG_BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Setup uvicorn loggers to use this format if desired
    logging.getLogger("uvicorn.access").handlers = [stdout_handler]


# Setup on import is removed to avoid redundant execution when module is imported


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ace.{name}")
