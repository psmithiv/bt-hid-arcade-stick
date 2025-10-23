Overview
========

The Bluetooth HID arcade stick project pairs CircuitPython firmware with a
Qt-based desktop debugger. Together they allow rapid iteration on hardware
inputs, BLE/USB HID reporting, and host-driven virtual button testing.

Data Flow
---------

.. code-block:: text

   Physical GPIO ┐
                 ├─> InputManager ──> HIDController ──┬─> BLE (optional)
   Virtual UI  ──┘                                    └─> USB HID (optional)
                                                      |
                                                 DebugInterface
                                                      |
                                           Virtual Controller UI

Firmware Responsibilities
-------------------------

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Module
     - Responsibility
   * - ``code``
     - Firmware entry point; loads configuration, wires managers together, and runs the cooperative loop.
   * - ``config``
     - Central configuration store for button ordering, pin mapping, debounce intervals, BLE/USB options, and log level.
   * - ``input_manager``
     - Polls GPIO-backed buttons (wired active-low with pull-ups) and emits debounced :class:`~input_manager.InputEvents`.
   * - ``hid_controller``
     - Maintains active button state, translates logical buttons to HID report IDs, dispatches updates to BLE/USB outputs, and notifies observers.
   * - ``ble_manager``
     - Orchestrates BLE advertising, pairing, and connection lifecycle; exposes the HID service to :mod:`hid_controller`.
   * - ``usb_hid_manager``
     - Mirrors HID reports over USB when the board is tethered for debugging.
   * - ``debug_interface``
     - Serial protocol for host tooling: accepts ``PRESS``/``RELEASE``/``STATE?`` commands, relays logs, and mirrors firmware state as JSON.
   * - ``firmware_logging``
     - Structured JSON logging utilities shared by firmware and host components.
   * - ``power_manager``
     - Placeholder for future battery and sleep management.

Host Tooling
------------

The desktop UI (``tools/virtual_controller.py``) provides:

* Serial bridge in a background thread that keeps Qt responsive.
* Controller layout with clickable buttons that send virtual ``PRESS`` and ``RELEASE`` commands.
* Log viewer with filter/search/save controls. Start the UI with ``--print-logs`` to mirror JSON lines to stdout.
* BLE status reporting based on events forwarded by :class:`ble_manager.BLEManager`.

See :doc:`reference` for module-level API documentation generated directly from the source.
