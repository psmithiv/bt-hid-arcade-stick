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
        report = self.usb_manager.reports[-1]
        self.assertEqual(report["buttons"], ["A"])
        self.assertEqual(report["inputs"], ["A"])
        self.assertEqual(report["hat"], 0x00)
        self.assertEqual(report["axes"], {"x": 0, "y": 0})

    def test_state_callback_invoked(self):
        events = InputEvents(pressed={"B"}, released=set())
        observed = []
        self.controller.set_state_callback(lambda buttons: observed.append(buttons))
        self.controller.process_inputs(events)
        self.assertEqual(observed[-1], ["B"])

    def test_shoulder_buttons_update_mask(self):
        events = InputEvents(pressed={"L2", "R2"}, released=set())
        self.controller.process_inputs(events)
        hid_buttons = CONTROLLER_CONFIG["hid_buttons"]
        l2_bit = 1 << hid_buttons.index("L2")
        r2_bit = 1 << hid_buttons.index("R2")
        self.assertEqual(self.controller._button_mask, l2_bit | r2_bit)

    def test_shoulder_press_updates_second_byte(self):
        events = InputEvents(pressed={"L1"}, released=set())
        self.controller.process_inputs(events)
        hid_device = usb_hid.devices[0]
        self.assertTrue(hid_device.reports)
        latest = hid_device.reports[-1]
        self.assertEqual(len(latest), 6)
        self.assertEqual(latest[0], 0x01)  # Report ID
        self.assertEqual(latest[1], 0x10)  # L1 maps to bit 4 (0x10) in low byte
        self.assertEqual(latest[2], 0x00)
        self.assertEqual(latest[3], 0xF0)  # Hat neutral with padding nibble
        self.assertEqual(latest[4], 0x00)
        self.assertEqual(latest[5], 0x00)

    def test_directional_buttons_behave_like_standard_buttons(self):
        events = InputEvents(pressed={"UP"}, released=set())
        self.controller.process_inputs(events)
        hid_buttons = CONTROLLER_CONFIG["hid_buttons"]
        up_bit = 1 << hid_buttons.index("UP")
        self.assertEqual(self.controller._button_mask, up_bit)
        report = self.usb_manager.reports[-1]
        self.assertEqual(report["buttons"], ["UP"])
        self.assertEqual(report["inputs"], ["UP"])
        self.assertEqual(report["hat"], 1)  # Hat points up
        self.assertEqual(report["axes"]["y"], -127)
        hid_device = usb_hid.devices[0]
        latest = hid_device.reports[-1]
        self.assertEqual(latest[0], 0x01)
        self.assertEqual(latest[1], 0x00)
        self.assertEqual(latest[2], 0x10)  # D-pad Up maps to bit 12 (0x10) in high byte
        self.assertEqual(latest[3], 0xF1)  # Hat = 1 (Up), pad nibble high
        self.assertEqual(latest[4], 0x00)  # X axis neutral
        self.assertEqual(latest[5], 0x81)  # Y axis -127 (two's complement)

    def test_diagonal_hat_updates_axes(self):
        events = InputEvents(pressed={"UP", "RIGHT"}, released=set())
        self.controller.process_inputs(events)
        report = self.usb_manager.reports[-1]
        self.assertEqual(report["hat"], 2)  # Up-right
        self.assertEqual(report["axes"], {"x": 127, "y": -127})
        hid_device = usb_hid.devices[0]
        latest = hid_device.reports[-1]
        self.assertEqual(latest[3], 0xF2)


if __name__ == "__main__":
    unittest.main()
