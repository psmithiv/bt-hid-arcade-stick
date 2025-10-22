"""Unit test scaffolding for the input manager module."""

try:
    import unittest
except ImportError:  # CircuitPython compatibility shim
    unittest = None  # pragma: no cover

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
