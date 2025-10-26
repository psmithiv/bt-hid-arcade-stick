"""
Test fixtures and environment setup for the Bluetooth HID arcade stick tests.

Provides lightweight stand-ins for CircuitPython-specific modules so the unit
tests can execute in a desktop Python interpreter without failing on missing
dependencies. The production firmware expects these modules to be supplied by
the board runtime.
"""

import types
import sys


def _register_module(name, module):
    """Register a module in sys.modules if it is not already present."""
    if name not in sys.modules:
        sys.modules[name] = module
    return sys.modules[name]


# ---------------------------------------------------------------------------
# CircuitPython board/digital I/O stubs

board_module = types.ModuleType("board")


def _board_getattr(name):
    return name


setattr(board_module, "__getattr__", _board_getattr)
_register_module("board", board_module)

digitalio_module = types.ModuleType("digitalio")


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


setattr(digitalio_module, "Pull", _Pull)
setattr(digitalio_module, "DigitalInOut", _DigitalInOut)
_register_module("digitalio", digitalio_module)


# ---------------------------------------------------------------------------
# Supervisor and USB HID stubs

supervisor_module = types.ModuleType("supervisor")


class _Runtime:
    def __init__(self):
        self.serial_connected = False
        self.serial_bytes_available = 0


setattr(supervisor_module, "runtime", _Runtime())
_register_module("supervisor", supervisor_module)

usb_hid_module = types.ModuleType("usb_hid")
setattr(usb_hid_module, "devices", ())
_register_module("usb_hid", usb_hid_module)


# ---------------------------------------------------------------------------
# Adafruit HID stub

adafruit_hid_module = types.ModuleType("adafruit_hid")
adafruit_hid_module.__path__ = []


def _find_device(devices, usage_page=None, usage=None):
    for device in devices:
        if getattr(device, "usage_page", None) == usage_page and getattr(device, "usage", None) == usage:
            return device
    raise ValueError("HID device not found")


setattr(adafruit_hid_module, "find_device", _find_device)
_register_module("adafruit_hid", adafruit_hid_module)


# ---------------------------------------------------------------------------
# Adafruit BLE stub

adafruit_ble_module = types.ModuleType("adafruit_ble")
setattr(adafruit_ble_module, "__version__", "0.0.0")
_register_module("adafruit_ble", adafruit_ble_module)


class _StubBLERadio:
    def __init__(self):
        self.connected = False
        self.connections = []
        self.advertising = False
        self._name = "StubBLE"

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    def start_advertising(self, advertisement, scan_response=None):
        self.advertising = True

    def stop_advertising(self):
        self.advertising = False

    def disconnect_all(self):
        self.connections = []

    def erase_bonding(self):
        pass


setattr(adafruit_ble_module, "BLERadio", _StubBLERadio)

advertising_module = types.ModuleType("adafruit_ble.advertising")


class _Advertisement:
    def __init__(self):
        pass


setattr(advertising_module, "Advertisement", _Advertisement)
_register_module("adafruit_ble.advertising", advertising_module)
setattr(adafruit_ble_module, "advertising", advertising_module)

advertising_standard_module = types.ModuleType("adafruit_ble.advertising.standard")


class _ProvideServicesAdvertisement:
    def __init__(self, *services):
        self.services = services
        self.complete_name = ""
        self.appearance = 0


setattr(
    advertising_standard_module,
    "ProvideServicesAdvertisement",
    _ProvideServicesAdvertisement,
)
_register_module("adafruit_ble.advertising.standard", advertising_standard_module)
setattr(advertising_module, "standard", advertising_standard_module)

services_module = types.ModuleType("adafruit_ble.services")
services_standard_module = types.ModuleType("adafruit_ble.services.standard")
_register_module("adafruit_ble.services", services_module)
_register_module("adafruit_ble.services.standard", services_standard_module)
setattr(adafruit_ble_module, "services", services_module)
setattr(services_module, "standard", services_standard_module)

device_info_module = types.ModuleType("adafruit_ble.services.standard.device_info")


class _DeviceInfoService:
    def __init__(self, software_revision="", manufacturer=""):
        self.software_revision = software_revision
        self.manufacturer = manufacturer


setattr(device_info_module, "DeviceInfoService", _DeviceInfoService)
_register_module("adafruit_ble.services.standard.device_info", device_info_module)
setattr(services_standard_module, "device_info", device_info_module)

hid_module = types.ModuleType("adafruit_ble.services.standard.hid")


class _HIDService:
    def __init__(self, *_, **__):
        self.devices = ()


setattr(hid_module, "HIDService", _HIDService)
_register_module("adafruit_ble.services.standard.hid", hid_module)
setattr(services_standard_module, "hid", hid_module)
