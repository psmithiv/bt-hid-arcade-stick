"""Translate logical button activity into HID reports.

Coordinates input events with the BLE and USB backends and maintains the
current controller state so redundant traffic is avoided. Button ordering
must match the HID report descriptor; see :mod:`config` for the wiring map.
"""

import struct

from adafruit_hid import find_device

from input_manager import InputEvents
from firmware_logging import get_logger


class _GamepadEndpoint:
    """
    Minimal HID gamepad endpoint inspired by Adafruit's reference implementation.

    Manages a 16-button bitfield and suppresses duplicate reports to conserve
    bandwidth over BLE and USB transports.
    """

    def __init__(self, devices):
        self._device = find_device(devices, usage_page=0x01, usage=0x05)
        self._report = bytearray(7)  # 1-byte report ID + 6-byte payload
        self._last_report = bytearray(len(self._report))
        self._buttons_state = 0
        self._reset_axes()
        self.reset_all()

    def reset_all(self):
        """Release all buttons and center joystick axes."""
        self._buttons_state = 0
        self._reset_axes()
        self._send(always=True)

    def set_buttons(self, buttons_state):
        """
        Update the button bitfield and send a report if anything changed.

        :param int buttons_state: Bitfield describing pressed buttons (1-indexed).
        """
        buttons_state &= 0xFFFF
        if buttons_state == self._buttons_state:
            return
        self._buttons_state = buttons_state
        self._send()

    def _reset_axes(self):
        self._joy_x = 0
        self._joy_y = 0
        self._joy_z = 0
        self._joy_rz = 0

    def _send(self, always=False):
        self._report[0] = 0x01  # Report ID expected by host
        struct.pack_into(
            "<Hbbbb",
            self._report,
            1,
            self._buttons_state,
            self._joy_x,
            self._joy_y,
            self._joy_z,
            self._joy_rz,
        )

        if always or self._report != self._last_report:
            self._device.send_report(self._report)
            self._last_report[:] = self._report


class HIDController:
    """Manage HID state and dispatch reports over BLE and USB."""

    def __init__(self, ble_manager, usb_manager, config):
        """
        Create the HID controller.

        :param ble_manager: Instance of :class:`ble_manager.BLEManager`.
        :param usb_manager: Instance of :class:`usb_hid_manager.USBHIDManager`.
        :param dict config: Controller configuration including ``buttons`` and ``hid`` blocks.
        """
        self._logger = get_logger("hid_controller")
        self._ble_manager = ble_manager
        self._usb_manager = usb_manager
        self._config = config or {}
        self._buttons = self._config.get("buttons", [])
        self._button_map = {name: index + 1 for index, name in enumerate(self._buttons)}
        self._active_buttons = set()
        self._state_callback = None
        self._button_mask = 0

        self._logger.info("Configuring HID controller with button layout: %s.", self._buttons)

        self._ble_gamepad = self._create_ble_gamepad()
        self._usb_gamepad = self._create_usb_gamepad()

    @property
    def button_names(self):
        """
        Return the ordered list of logical button names.

        :returns: List of button identifiers matching the HID descriptor order.
        :rtype: list[str]
        """
        return list(self._buttons)

    @property
    def active_buttons(self):
        """
        Return a snapshot of currently active buttons.

        :returns: Set of logical button names that are currently pressed.
        :rtype: set[str]
        """
        return set(self._active_buttons)

    def set_state_callback(self, callback):
        """
        Register a callback invoked when button state changes.

        :param callable callback: Function accepting a sorted list of active buttons.
        """
        self._state_callback = callback

    def inject_virtual_event(self, pressed=None, released=None):
        """
        Simulate button events for debugging/testing.

        :param Iterable[str] pressed: Logical buttons to mark as pressed.
        :param Iterable[str] released: Logical buttons to mark as released.
        """
        pressed = {name for name in (pressed or []) if name in self._button_map}
        released = {name for name in (released or []) if name in self._button_map}
        if not pressed and not released:
            return
        self.process_inputs(InputEvents(pressed=pressed, released=released))

    def _create_ble_gamepad(self):
        """Instantiate a BLE gamepad interface via the BLE manager."""
        hid_service = getattr(self._ble_manager, "hid_service", None)
        if hid_service is None:
            self._logger.warning("BLE HID service is unavailable; BLE reports disabled.")
            return None
        try:
            gamepad = _GamepadEndpoint(hid_service.devices)
            self._logger.debug("BLE gamepad interface initialized.")
            return gamepad
        except Exception as exc:  # pragma: no cover - runtime specific
            self._logger.error("Failed to initialize BLE gamepad: %s.", exc)
            return None

    def _create_usb_gamepad(self):
        """Instantiate a USB gamepad interface if USB HID is enabled."""
        hid_config = self._config.get("hid", {})
        if not hid_config.get("usb_enabled", True):
            self._logger.info("USB HID output disabled by configuration.")
            return None

        import usb_hid  # type: ignore

        try:
            gamepad = _GamepadEndpoint(usb_hid.devices)
            self._logger.debug("USB gamepad interface initialized.")
            return gamepad
        except Exception as exc:  # pragma: no cover - runtime specific
            self._logger.error("Failed to initialize USB gamepad: %s.", exc)
            return None

    def process_inputs(self, input_events):
        """
        Update internal button state and emit HID reports as needed.

        :param InputEvents input_events: Debounced button transitions from :mod:`input_manager`.
        """
        pending_update = False

        if input_events.pressed:
            self._logger.info("Buttons pressed: %s.", sorted(input_events.pressed))
            self._active_buttons.update(input_events.pressed)
            pending_update = True

        if input_events.released:
            self._logger.info("Buttons released: %s.", sorted(input_events.released))
            self._active_buttons.difference_update(input_events.released)
            pending_update = True

        if pending_update:
            self._button_mask = self._build_button_mask(self._active_buttons)
            self._logger.debug(
                "Active buttons: %s (mask=0x%04X).", sorted(self._active_buttons), self._button_mask
            )
            self._send_report()
            self._notify_state_change()

    def _send_report(self):
        """Dispatch button state changes to BLE and USB gamepads."""
        if self._ble_manager.connected and self._ble_gamepad:
            self._logger.debug("Dispatching BLE button mask 0x%04X.", self._button_mask)
            self._ble_gamepad.set_buttons(self._button_mask)

        if self._usb_gamepad:
            self._logger.debug("Dispatching USB button mask 0x%04X.", self._button_mask)
            self._usb_gamepad.set_buttons(self._button_mask)

        report_snapshot = {"buttons": sorted(self._active_buttons)}
        self._usb_manager.send_report(report_snapshot)

    def _build_button_mask(self, active_buttons):
        """Translate the current active button set to the HID bitmask."""
        mask = 0
        for name in active_buttons:
            button_id = self._button_map.get(name)
            if button_id is None:
                continue
            mask |= 1 << (button_id - 1)
        return mask

    def _notify_state_change(self):
        """Notify observers of button state changes."""
        if self._state_callback is None:
            return
        try:
            self._state_callback(sorted(self._active_buttons))
        except Exception as exc:  # pragma: no cover - callback safety
            self._logger.warning("State callback invocation failed: %s.", exc)
