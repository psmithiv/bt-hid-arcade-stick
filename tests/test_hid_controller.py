"""Unit test scaffolding for the HID controller module."""

try:
    import unittest
except ImportError:  # CircuitPython compatibility shim
    unittest = None  # pragma: no cover

from hid_controller import HIDController
from config import CONTROLLER_CONFIG
from input_manager import InputEvents


class DummyHIDService:
    """Minimal HIDService stand-in with devices attribute."""

    def __init__(self):
        self.devices = ()


class DummyBLEManager:
    """Simple stand-in for BLE manager during tests."""

    def __init__(self):
        self.connected = False
        self.hid_service = DummyHIDService()


class RecordingUSBManager:
    """Captures reports sent through the USB manager interface."""

    def __init__(self):
        self.reports = []

    def send_report(self, report):
        self.reports.append(report)


@unittest.skipIf(unittest is None, "unittest not available in this environment")
class HIDControllerTest(unittest.TestCase):
    """Placeholder tests verifying high-level interactions."""

    def setUp(self):
        self.ble_manager = DummyBLEManager()
        self.usb_manager = RecordingUSBManager()
        self.controller = HIDController(self.ble_manager, self.usb_manager, CONTROLLER_CONFIG)

    def test_process_inputs_records_active_buttons(self):
        events = InputEvents(pressed={"A"}, released=set())
        self.controller.process_inputs(events)
        self.assertEqual(self.usb_manager.reports[-1]["buttons"], ["A"])

    def test_state_callback_invoked(self):
        events = InputEvents(pressed={"B"}, released=set())
        observed = []
        self.controller.set_state_callback(lambda buttons: observed.append(buttons))
        self.controller.process_inputs(events)
        self.assertEqual(observed[-1], ["B"])


if __name__ == "__main__":
    if unittest is not None:
        unittest.main()
