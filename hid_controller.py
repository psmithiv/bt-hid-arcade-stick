"""
HID report orchestration for the Bluetooth HID arcade stick.
Coordinates input events with BLE/USB backends and maintains the most
recent controller state to avoid redundant traffic.
"""

from input_manager import InputEvents
from firmware_logging import get_logger

try:
    from adafruit_hid.gamepad import Gamepad
except ImportError:  # pragma: no cover - host environment / unit tests
    Gamepad = None


class HIDController:
    """Manage HID state and dispatch reports over BLE and USB."""

    def __init__(self, ble_manager, usb_manager, config):
        self._logger = get_logger("hid_controller")
        self._ble_manager = ble_manager
        self._usb_manager = usb_manager
        self._config = config or {}
        self._buttons = self._config.get("buttons", [])
        self._button_map = {
            name: index + 1 for index, name in enumerate(self._buttons)
        }
        self._active_buttons = set()
        self._state_callback = None

        self._logger.info("Configuring HID controller with button layout: %s.", self._buttons)

        self._ble_gamepad = self._create_ble_gamepad()
        self._usb_gamepad = self._create_usb_gamepad()

    @property
    def button_names(self):
        """Return the ordered list of logical button names."""
        return list(self._buttons)

    @property
    def active_buttons(self):
        """Return a snapshot of currently active buttons."""
        return set(self._active_buttons)

    def set_state_callback(self, callback):
        """Register a callback invoked when button state changes."""
        self._state_callback = callback

    def inject_virtual_event(self, pressed=None, released=None):
        """Simulate button events for debugging/testing."""
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
        if Gamepad is None:
            self._logger.warning("adafruit_hid.Gamepad module is unavailable; BLE reports disabled.")
            return None
        try:
            gamepad = Gamepad(hid_service.devices)
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
        if Gamepad is None:
            self._logger.warning("adafruit_hid.Gamepad module is unavailable; USB reports disabled.")
            return None

        try:
            import usb_hid  # type: ignore
        except ImportError:  # pragma: no cover - host environment / unit tests
            self._logger.warning("usb_hid module is unavailable; USB reports disabled.")
            return None

        try:
            gamepad = Gamepad(usb_hid.devices)
            self._logger.debug("USB gamepad interface initialized.")
            return gamepad
        except Exception as exc:  # pragma: no cover - runtime specific
            self._logger.error("Failed to initialize USB gamepad: %s.", exc)
            return None

    def process_inputs(self, input_events):
        """
        Update internal button state and emit HID reports as needed.
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
            self._logger.debug("Active buttons: %s.", sorted(self._active_buttons))
            self._send_report(input_events)
            self._notify_state_change()

    def _send_report(self, input_events):
        """Dispatch button state changes to BLE and USB gamepads."""
        buttons_to_press = self._resolve_button_ids(input_events.pressed)
        buttons_to_release = self._resolve_button_ids(input_events.released)

        if self._ble_manager.connected and self._ble_gamepad:
            self._logger.debug(
                "Dispatching BLE report press=%s release=%s.",
                buttons_to_press,
                buttons_to_release,
            )
            self._apply_gamepad_update(self._ble_gamepad, buttons_to_press, buttons_to_release)

        if self._usb_gamepad:
            self._logger.debug(
                "Dispatching USB report press=%s release=%s.",
                buttons_to_press,
                buttons_to_release,
            )
            self._apply_gamepad_update(self._usb_gamepad, buttons_to_press, buttons_to_release)

        report_snapshot = {"buttons": sorted(self._active_buttons)}
        self._usb_manager.send_report(report_snapshot)

    def _resolve_button_ids(self, button_names):
        """Translate logical button names to gamepad button IDs."""
        return [self._button_map[name] for name in button_names if name in self._button_map]

    @staticmethod
    def _apply_gamepad_update(gamepad, buttons_to_press, buttons_to_release):
        """Apply button changes to a Gamepad instance."""
        if buttons_to_press:
            gamepad.press_buttons(*buttons_to_press)
        if buttons_to_release:
            gamepad.release_buttons(*buttons_to_release)

    def _notify_state_change(self):
        """Notify observers of button state changes."""
        if self._state_callback is None:
            return
        try:
            self._state_callback(sorted(self._active_buttons))
        except Exception as exc:  # pragma: no cover - callback safety
            self._logger.warning("State callback invocation failed: %s.", exc)
