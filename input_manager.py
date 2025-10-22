"""
Input management layer for the Bluetooth HID arcade stick.
Responsible for initializing GPIO inputs and exposing debounced button
state changes to upstream consumers.
"""

from collections import namedtuple

from firmware_logging import get_logger

InputEvents = namedtuple("InputEvents", ["pressed", "released"])


class InputManager:
    """Placeholder input manager; hardware interactions to be implemented."""

    def __init__(self, config):
        self._config = config
        self._logger = get_logger("input_manager")
        self._logger.debug("Input manager initialized with configuration: %s.", self._config)

    def poll(self):
        """
        Poll hardware inputs and return debounced button transitions.
        Currently returns an empty snapshot until hardware integration lands.
        """
        return InputEvents(pressed=set(), released=set())
