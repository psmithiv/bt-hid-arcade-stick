"""
Lightweight logging utilities for the Bluetooth HID arcade stick.
Provides printf-style formatting across standard logging levels with an
optional sink callback so host tooling can mirror firmware logs.
"""

import time

DEBUG = 10
INFO = 20
WARNING = 30
ERROR = 40
CRITICAL = 50

_LEVEL_NAMES = {
    DEBUG: "DEBUG",
    INFO: "INFO",
    WARNING: "WARNING",
    ERROR: "ERROR",
    CRITICAL: "CRITICAL",
}

_NAME_TO_LEVEL = {name: level for level, name in _LEVEL_NAMES.items()}

_current_level = INFO
_sink = None


def set_level(level):
    """
    Configure the global logging level.
    Accepts either a numeric level or a case-insensitive textual level.
    """
    global _current_level
    _current_level = _coerce_level(level)


def get_level():
    """Return the currently active logging level."""
    return _current_level


def get_level_name(level):
    """Translate a numeric level to a printable name."""
    return _LEVEL_NAMES.get(level, str(level))


def get_level_by_name(name):
    """Translate a textual level name to its numeric representation."""
    if name is None:
        raise ValueError("Level name must not be None")
    try:
        return _NAME_TO_LEVEL[name.upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown log level: {name}") from exc


def set_sink(sink):
    """
    Register a callable invoked with (level, logger_name, message) for
    every emitted log record. Passing None clears the sink.
    """
    global _sink
    _sink = sink


def get_sink():
    """Return the currently registered sink (if any)."""
    return _sink


class Logger:
    """Minimal logger that tags messages with a name."""

    def __init__(self, name):
        self._name = name
        self._log = _emit

    def debug(self, message, *args):
        self._log(DEBUG, self._name, message, args)

    def info(self, message, *args):
        self._log(INFO, self._name, message, args)

    def warning(self, message, *args):
        self._log(WARNING, self._name, message, args)

    warn = warning  # Compatibility alias.

    def error(self, message, *args):
        self._log(ERROR, self._name, message, args)

    def critical(self, message, *args):
        self._log(CRITICAL, self._name, message, args)

    fatal = critical  # Compatibility alias.

    def log(self, level, message, *args):
        """Emit a message at an arbitrary level."""
        numeric_level = _coerce_level(level)
        self._log(numeric_level, self._name, message, args)


def get_logger(name):
    """Obtain a logger scoped by name."""
    return Logger(name)


def _emit(level, name, message, args):
    if level < _current_level:
        return

    level_name = get_level_name(level)
    text = _format(message, args)
    parts = [f"[{level_name}]"]
    if name:
        parts.append(name)
    if hasattr(time, "monotonic"):
        parts.append("@{:.3f}s".format(time.monotonic()))
    parts.append(text)

    print(" ".join(parts))

    if _sink is not None:
        try:
            _sink(level, name, text)
        except Exception:
            # Logging failures must never bubble into the firmware loop.
            pass


def _format(message, args):
    if not args:
        return message
    try:
        return message % args
    except Exception:
        # Fallback that won't raise even if formatting fails.
        rendered = ", ".join(repr(arg) for arg in args)
        return "{} [{}]".format(message, rendered)


def _coerce_level(level):
    """Normalize textual or numeric levels to their integer representation."""
    if isinstance(level, str):
        return get_level_by_name(level)
    return int(level)
