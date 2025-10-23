"""
Lightweight logging utilities for the Bluetooth HID arcade stick.
Messages are emitted directly to the serial console as structured JSON
records prefixed with ``LOG `` so any listener can consume them.
"""

import json
import sys
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

    record = {
        "level": get_level_name(level),
        "logger": name,
        "message": _format(message, args),
    }

    if hasattr(time, "monotonic"):
        record["timestamp"] = time.monotonic()

    # Remove keys with falsy/None values except message.
    payload = {k: v for k, v in record.items() if v is not None}
    payload.setdefault("type", "log")
    _write_payload(payload)


def _write_payload(payload):
    """Emit the JSON payload while handling serial transport quirks."""
    serialized = json.dumps(payload)
    try:
        print(serialized)
    except OSError as exc:
        # CircuitPython occasionally raises OSError 22 when flushing the USB CDC port.
        if not exc.args or exc.args[0] != 22:
            raise
        # Fall back to a raw write; ignore further transport errors to keep firmware running.
        try:
            sys.stdout.write(serialized + "\n")
        except OSError:
            return
    _try_flush()


def _try_flush():
    """Best-effort flush for stdout; tolerate transports that do not support it."""
    try:
        sys.stdout.flush()
    except (AttributeError, OSError):
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
