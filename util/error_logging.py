"""Centralized error logging for handled and unhandled exceptions."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import tempfile
import threading
from types import TracebackType
from typing import Optional, Type

LOGGER_NAME = "floowandereeze"
LOG_DIRECTORY_NAME = "logs"
LOG_FILE_NAME = "error.log"
_HANDLER_MARKER = "_floowandereeze_error_handler"


def _application_directory() -> Path:
    """Return the directory that owns runtime files for this launch mode."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _create_log_directory() -> Path:
    """Create the preferred log directory, falling back to the temp folder."""
    preferred_directory = _application_directory() / LOG_DIRECTORY_NAME
    try:
        preferred_directory.mkdir(parents=True, exist_ok=True)
        return preferred_directory
    except OSError:
        fallback_directory = (
            Path(tempfile.gettempdir())
            / "FloowandereezeAndModding"
            / LOG_DIRECTORY_NAME
        )
        fallback_directory.mkdir(parents=True, exist_ok=True)
        return fallback_directory


def get_error_log_path() -> Path:
    """Return the error log path, creating its parent directory if necessary."""
    return _create_log_directory() / LOG_FILE_NAME


def _log_uncaught_exception(
    exception_type: Type[BaseException],
    exception: BaseException,
    traceback: Optional[TracebackType],
) -> None:
    """Write an uncaught exception to the error log."""
    if issubclass(exception_type, KeyboardInterrupt):
        sys.__excepthook__(exception_type, exception, traceback)
        return

    logging.getLogger(LOGGER_NAME).critical(
        "Uncaught exception caused the application to stop",
        exc_info=(exception_type, exception, traceback),
    )
    sys.__excepthook__(exception_type, exception, traceback)


def _log_thread_exception(args: threading.ExceptHookArgs) -> None:
    """Write an uncaught background-thread exception to the error log."""
    if args.exc_type is SystemExit:
        return

    logging.getLogger(LOGGER_NAME).critical(
        "Uncaught exception in thread %s",
        args.thread.name if args.thread else "unknown",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    threading.__excepthook__(args)


def _log_unraisable_exception(args) -> None:
    """Write exceptions that Python could not otherwise raise."""
    logging.getLogger(LOGGER_NAME).error(
        "Unraisable exception in %s: %s",
        args.object,
        args.err_msg or "no additional details",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    sys.__unraisablehook__(args)


def setup_error_logging() -> Path:
    """Configure the rotating error log and global exception hooks."""
    logger = logging.getLogger()
    existing_handler = next(
        (
            handler
            for handler in logger.handlers
            if getattr(handler, _HANDLER_MARKER, False)
        ),
        None,
    )

    if existing_handler is None:
        log_path = get_error_log_path()
        handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
            delay=True,
        )
        setattr(handler, _HANDLER_MARKER, True)
        handler.setLevel(logging.ERROR)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | "
                "%(filename)s:%(lineno)d | %(message)s"
            )
        )
        logger.addHandler(handler)
    else:
        log_path = Path(existing_handler.baseFilename)

    if logger.level > logging.ERROR:
        logger.setLevel(logging.ERROR)

    sys.excepthook = _log_uncaught_exception
    threading.excepthook = _log_thread_exception
    sys.unraisablehook = _log_unraisable_exception
    return log_path
