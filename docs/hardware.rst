Hardware Wiring
===============

The firmware assumes the arcade stick buttons are wired **active-low** with
pull-up resistors. Update :data:`config.PIN_MAP` to match your exact wiring
before flashing the firmware.

Default Pin Map
---------------

.. list-table::
   :header-rows: 1
   :widths: 25 25

   * - Button
     - Pin
   * - UP
     - D5
   * - DOWN
     - D6
   * - LEFT
     - D9
   * - RIGHT
     - D10
   * - A
     - D11
   * - B
     - D12
   * - X
     - D13 (on-board LED, useful for testing)
   * - Y
     - D0
   * - L1
     - D1
   * - R1
     - D4
   * - L2
     - A0
   * - R2
     - A1
   * - START
     - A2
   * - SELECT
     - A3
   * - HOME
     - A4
   * - PAIRING
     - A5 (optional dedicated pairing button)

Pairing Button
--------------

If you connect a dedicated pairing push-button, configure
:data:`config.PAIRING_BUTTON_PIN` accordingly. The button must be wired
active-low; press and hold it for ``config.PAIRING_HOLD_MS`` milliseconds to
trigger pairing mode. The :class:`ble_manager.BLEManager` handles debouncing
and timeout logic automatically.

Guidelines
----------

* Keep wiring short and avoid sharing grounds across high-current paths.
* When testing without full hardware, you can temporarily map buttons to the
  on-board LED or other accessible pins for quick validation.
* The debug interface mirrors button state back to the host; use the virtual
  controller UI to confirm wiring changes without rebuilding firmware.
