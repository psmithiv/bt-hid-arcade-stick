"""
Input management layer for the Bluetooth HID arcade stick.
Responsible for initializing GPIO inputs and exposing debounced button
state changes to upstream consumers.
"""

import time
from collections import namedtuple

from firmware_logging import get_logger

InputEvents = namedtuple("InputEvents", ["pressed", "released"])

try:  # CircuitPython hardware modules (not available in host tests)
    import board  # type: ignore
except ImportError:  # pragma: no cover - host environment
    board = None  # type: ignore

try:
    import digitalio  # type: ignore
except ImportError:  # pragma: no cover - host environment
    digitalio = None  # type: ignore


class InputManager:
    """Poll GPIO-backed buttons and emit debounced transitions."""

    def __init__(self, config):
        self._config = config or {}
        self._logger = get_logger("input_manager")

        self._buttons = list(self._config.get("buttons", []))
        pin_map = self._config.get("pin_map", {})
        self._debounce_seconds = max(self._config.get("debounce_ms", 10), 0) / 1000.0

        self._pin_map = {}
        self._pin_objects = {}
        self._raw_state = {}
        self._stable_state = {}
        self._last_transition = {}

        if not self._buttons:
            self._logger.warning("No buttons configured; input polling disabled.")
            return

        if digitalio is None:
            self._logger.warning("digitalio module unavailable; hardware buttons will not be polled.")
            return

        self._initialize_pins(pin_map)

    # ------------------------------------------------------------------ #
    # Public API

    def poll(self):
        """
        Poll hardware inputs and return debounced button transitions.
        """
        if not self._pin_objects:
            return InputEvents(pressed=set(), released=set())

        now = time.monotonic()
        pressed = set()
        released = set()

        for button in self._buttons:
            pin = self._pin_objects.get(button)
            if pin is None:
                continue

            raw_value = pin.value
            previous_raw = self._raw_state[button]
            if raw_value != previous_raw:
                self._raw_state[button] = raw_value
                self._last_transition[button] = now
                continue  # Require debounce interval before acting.

            if (now - self._last_transition[button]) < self._debounce_seconds:
                continue

            pressed_now = not raw_value  # Buttons wired as active-low by default.
            previous_stable = self._stable_state[button]
            if pressed_now == previous_stable:
                continue

            self._stable_state[button] = pressed_now
            if pressed_now:
                pressed.add(button)
                self._logger.debug("Button pressed: %s", button)
            else:
                released.add(button)
                self._logger.debug("Button released: %s", button)

        if pressed or released:
            self._logger.debug("Debounced snapshot pressed=%s released=%s", sorted(pressed), sorted(released))

        return InputEvents(pressed=pressed, released=released)

    # ------------------------------------------------------------------ #
    # Internal helpers

    def _initialize_pins(self, pin_map):
        for button in self._buttons:
            raw_pin = pin_map.get(button)
            if raw_pin is None:
                continue

            resolved = self._resolve_pin(raw_pin)
            if resolved is None:
                self._logger.warning("Unable to resolve pin '%s' for button %s; skipping hardware polling.", raw_pin, button)
                continue

            try:
                dio = digitalio.DigitalInOut(resolved)  # type: ignore[arg-type]
                dio.switch_to_input(pull=digitalio.Pull.UP)
            except Exception as exc:  # pragma: no cover - hardware specific
                self._logger.error("Failed to initialize pin %s for button %s: %s", resolved, button, exc)
                continue

            self._pin_map[button] = resolved
            self._pin_objects[button] = dio
            raw = dio.value
            pressed = not raw
            self._raw_state[button] = raw
            self._stable_state[button] = pressed
            self._last_transition[button] = time.monotonic()
            self._logger.debug("Configured button '%s' on pin %s (initial pressed=%s)", button, resolved, pressed)

        if not self._pin_objects:
            self._logger.warning("No hardware pins were initialized; input polling will be inert.")

    def _resolve_pin(self, raw_pin):
        """
        Convert a pin reference from config into a board pin object.
        Accepts board pin objects or string names (e.g. 'D5').
        """
        if isinstance(raw_pin, str):
            if board is None:
                self._logger.error("Board module unavailable; cannot resolve pin name '%s'.", raw_pin)
                return None
            attribute = raw_pin
            if not hasattr(board, attribute):
                attribute = raw_pin.upper()
            resolved = getattr(board, attribute, None)
            if resolved is None:
                self._logger.error("Board does not expose pin named '%s'.", raw_pin)
                return None
            return resolved
        return raw_pin
