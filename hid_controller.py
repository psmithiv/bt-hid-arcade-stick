"""Translate logical button activity into HID reports.

Coordinates input events with the BLE and USB backends and maintains the
current controller state so redundant traffic is avoided. Button ordering
must match the HID report descriptor; see :mod:`config` for the wiring map.
"""

import struct

from adafruit_hid import find_device

from input_manager import InputEvents
from firmware_logging import get_logger
from hid_report import GAMEPAD_INPUT_REPORT_LENGTH, GAMEPAD_REPORT_ID


class _GamepadEndpoint:
    """
    Minimal HID gamepad endpoint inspired by Adafruit's reference implementation.

    Manages a 16-button bitfield, hat switch, and X/Y axes while suppressing
    duplicate reports to conserve bandwidth over BLE and USB transports.
    """

    def __init__(self, devices):
        self._device = find_device(devices, usage_page=0x01, usage=0x05)
        self._report = bytearray(GAMEPAD_INPUT_REPORT_LENGTH)
        self._last_report = bytearray(len(self._report))
        self._buttons_state = 0
        self._hat_state = 0x08  # Neutral hat (null state per HID spec)
        self._axes_state = (0, 0)  # X, Y axes (signed)
        self.reset_all()

    def reset_all(self):
        """Release all buttons, neutralize the hat/axes, and send a neutral report."""
        self._buttons_state = 0
        self._hat_state = 0x08
        self._axes_state = (0, 0)
        self._send(always=True)

    def set_state(self, buttons_state, hat_state, axes_state):
        """
        Update the HID state and send a report if anything changed.

        :param int buttons_state: Button bitfield (1-indexed ordering).
        :param int hat_state: Hat switch value (0-7 directions, 8 = neutral).
        :param tuple[int, int] axes_state: Signed X/Y axis values (-127 to 127).
        """
        buttons_state &= 0xFFFF
        hat_state = hat_state & 0x0F
        if not isinstance(axes_state, (tuple, list)) or len(axes_state) != 2:
            axes_state = (0, 0)
        x_axis = _clamp_axis(axes_state[0])
        y_axis = _clamp_axis(axes_state[1])
        axes_state = (x_axis, y_axis)

        if (
            buttons_state == self._buttons_state
            and hat_state == self._hat_state
            and axes_state == self._axes_state
        ):
            return
        self._buttons_state = buttons_state
        self._hat_state = hat_state
        self._axes_state = axes_state
        self._send()

    def _send(self, always=False):
        self._report[0] = GAMEPAD_REPORT_ID  # Report ID expected by host
        struct.pack_into(
            "<H",
            self._report,
            1,
            self._buttons_state,
        )
        # Upper nibble is padding (reserved high), HID spec recommends 0xF when unused.
        self._report[3] = (self._hat_state & 0x0F) | 0xF0
        struct.pack_into(
            "<bb",
            self._report,
            4,
            self._axes_state[0],
            self._axes_state[1],
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
        self._buttons = list(self._config.get("hid_buttons", self._config.get("buttons", [])))
        self._valid_inputs = set(self._buttons)
        self._button_map = {name: index + 1 for index, name in enumerate(self._buttons)}
        self._active_buttons = set()
        self._state_callback = None
        self._button_mask = 0
        self._hat_neutral = int(self._config.get("hat_neutral", 0x08))
        self._hat_state = self._hat_neutral
        self._axes_state = (0, 0)
        self._axis_min = _clamp_axis(self._config.get("axis_min", -127))
        self._axis_max = _clamp_axis(self._config.get("axis_max", 127))
        if self._axis_min >= self._axis_max:
            self._axis_min, self._axis_max = -127, 127
        self._dpad_up = self._config.get("dpad_up", "UP")
        self._dpad_down = self._config.get("dpad_down", "DOWN")
        self._dpad_left = self._config.get("dpad_left", "LEFT")
        self._dpad_right = self._config.get("dpad_right", "RIGHT")

        self._logger.info("Configuring HID controller with buttons=%s.", self._buttons)

        self._ble_gamepad = self._create_ble_gamepad()
        self._usb_gamepad = self._create_usb_gamepad()

    @property
    def button_names(self):
        """
        Return the ordered list of HID button names.

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

    @property
    def hat_state(self):
        """
        Return the current hat switch value (1-8 directions, 0 = neutral).

        :returns: Integer hat value compatible with HID hat switch usage.
        :rtype: int
        """
        return int(self._hat_state)

    @property
    def axis_state(self):
        """
        Return the current signed X/Y axis tuple.

        :returns: Tuple ``(x, y)`` where each element is in the -127..127 range.
        :rtype: tuple[int, int]
        """
        return (int(self._axes_state[0]), int(self._axes_state[1]))

    def ordered_active_inputs(self):
        """
        Return the ordered list of active HID buttons.

        :returns: Ordered list of logical inputs currently pressed.
        :rtype: list[str]
        """
        return self._ordered_active_buttons()

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
        pressed = {name for name in (pressed or []) if name in self._valid_inputs}
        released = {name for name in (released or []) if name in self._valid_inputs}
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
            ordered_buttons = self._ordered_active_buttons()
            # For modern hosts we publish hat and axis data derived from the D-pad.
            self._hat_state = self._compute_hat_state()
            self._axes_state = self._compute_axis_state()
            self._logger.debug(
                "Active buttons: %s (mask=0x%04X hat=%s axes=%s).",
                ordered_buttons,
                self._button_mask,
                self._hat_state,
                self._axes_state,
            )
            self._send_report(ordered_buttons)
            self._notify_state_change(ordered_buttons)

    def _send_report(self, ordered_buttons):
        """Dispatch button state changes to BLE and USB gamepads."""
        if self._ble_manager.connected and self._ble_gamepad:
            self._logger.debug(
                "Dispatching BLE state mask=0x%04X hat=%s axes=%s.",
                self._button_mask,
                self._hat_state,
                self._axes_state,
            )
            self._ble_gamepad.set_state(self._button_mask, self._hat_state, self._axes_state)

        if self._usb_gamepad:
            self._logger.debug(
                "Dispatching USB state mask=0x%04X hat=%s axes=%s.",
                self._button_mask,
                self._hat_state,
                self._axes_state,
            )
            self._usb_gamepad.set_state(self._button_mask, self._hat_state, self._axes_state)

        report_snapshot = {
            "buttons": list(ordered_buttons),
            "inputs": list(ordered_buttons),
            "hat": self._hat_state,
            "axes": {
                "x": self._axes_state[0],
                "y": self._axes_state[1],
            },
        }
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

    def _notify_state_change(self, ordered_inputs):
        """Notify observers of button state changes."""
        if self._state_callback is None:
            return
        try:
            self._state_callback(list(ordered_inputs))
        except Exception as exc:  # pragma: no cover - callback safety
            self._logger.warning("State callback invocation failed: %s.", exc)

    def _ordered_active_buttons(self):
        """Return active buttons ordered according to the HID descriptor."""
        if not self._active_buttons:
            return []
        return [name for name in self._buttons if name in self._active_buttons]

    # ------------------------------------------------------------------
    # Internal helpers for derived state

    def _compute_hat_state(self):
        """Convert the active D-pad buttons into a HID hat value."""
        up, down, left, right = self._dpad_status()
        if up and right:
            return 2
        if right and down:
            return 4
        if down and left:
            return 6
        if left and up:
            return 8
        if up:
            return 1
        if right:
            return 3
        if down:
            return 5
        if left:
            return 7
        return self._hat_neutral  # Neutral

    def _compute_axis_state(self):
        """Generate signed X/Y axis values from the D-pad."""
        up, down, left, right = self._dpad_status()
        x_axis = self._axis_value(left, right)
        y_axis = self._axis_value(up, down)
        return (x_axis, y_axis)

    def _dpad_status(self):
        """Return booleans describing D-pad activation, canceling opposites."""
        up = self._dpad_up in self._active_buttons
        down = self._dpad_down in self._active_buttons
        left = self._dpad_left in self._active_buttons
        right = self._dpad_right in self._active_buttons

        if up and down:
            up = down = False
        if left and right:
            left = right = False
        return up, down, left, right

    def _axis_value(self, negative_active, positive_active):
        """Helper translating digital inputs to signed axis values."""
        if negative_active == positive_active:
            return 0
        return self._axis_min if negative_active else self._axis_max


def _clamp_axis(value, minimum=-127, maximum=127):
    """Clamp axis values to the signed 8-bit HID range."""
    try:
        numeric = int(value)
    except Exception:
        numeric = 0
    if numeric < minimum:
        return minimum
    if numeric > maximum:
        return maximum
    return numeric
