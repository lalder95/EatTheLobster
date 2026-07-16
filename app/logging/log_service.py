import logging
import logging.handlers

from app.config import LOG_DIR, _ensure_dirs


def setup_logging(level: int = logging.INFO) -> None:
    _ensure_dirs()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    # Avoid adding duplicate handlers on hot-reload
    if root.handlers:
        return

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    log_file = LOG_DIR / "etl_importer.log"
    file_handler = logging.handlers.RotatingFileHandler(
        str(log_file),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root.setLevel(level)
    root.addHandler(console_handler)
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
