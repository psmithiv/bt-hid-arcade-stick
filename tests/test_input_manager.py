"""Unit test scaffolding for the input manager module."""

import sys
import types

import unittest

# Provide lightweight stubs for CircuitPython-specific modules.
board = types.ModuleType("board")


def _board_getattr(name):
    return name


setattr(board, "__getattr__", _board_getattr)
sys.modules.setdefault("board", board)

digitalio = types.ModuleType("digitalio")


class _Pull:
    UP = "UP"


class _DigitalInOut:
    def __init__(self, pin):
        self._value = True

    def switch_to_input(self, pull=None):
        pass

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = bool(new_value)


setattr(digitalio, "Pull", _Pull)
setattr(digitalio, "DigitalInOut", _DigitalInOut)
sys.modules.setdefault("digitalio", digitalio)

from input_manager import InputManager, InputEvents
from config import CONTROLLER_CONFIG


@unittest.skipIf(unittest is None, "unittest not available in this environment")
class InputManagerTest(unittest.TestCase):
    """Placeholder tests that will grow with implementation."""

    def setUp(self):
        self.manager = InputManager(CONTROLLER_CONFIG)

    def test_poll_returns_input_events(self):
        events = self.manager.poll()
        self.assertIsInstance(events, InputEvents)
        self.assertFalse(events.pressed)
        self.assertFalse(events.released)


if __name__ == "__main__":
    if unittest is not None:
        unittest.main()
