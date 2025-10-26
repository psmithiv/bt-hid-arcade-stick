"""Unit test scaffolding for the HID controller module."""

import unittest

import usb_hid

from hid_controller import HIDController
from config import CONTROLLER_CONFIG
from input_manager import InputEvents


class DummyHIDDevice:
    """Simple HID device that records outgoing reports."""

    usage_page = 0x01
    usage = 0x05

    def __init__(self):
        self.reports = []

    def send_report(self, report):
        self.reports.append(bytes(report))


class DummyHIDService:
    """Minimal HIDService stand-in exposing available devices."""

    def __init__(self):
        self.devices = (DummyHIDDevice(),)


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


class HIDControllerTest(unittest.TestCase):
    """Placeholder tests verifying high-level interactions."""

    def setUp(self):
        usb_hid.devices = (DummyHIDDevice(),)
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

    def test_shoulder_buttons_update_mask(self):
        events = InputEvents(pressed={"L2", "R2"}, released=set())
        self.controller.process_inputs(events)
        l2_bit = 1 << CONTROLLER_CONFIG["buttons"].index("L2")
        r2_bit = 1 << CONTROLLER_CONFIG["buttons"].index("R2")
        self.assertEqual(self.controller._button_mask, l2_bit | r2_bit)


if __name__ == "__main__":
    unittest.main()
