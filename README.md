# Bluetooth HID Arcade Stick Firmware

This project is a CircuitPython-based firmware and companion desktop tooling for a Bluetooth / USB arcade stick. It provides:

- A modular firmware that maps physical inputs to Bluetooth Low Energy (BLE) and USB HID reports.
- A serial debug interface that exposes state, accepts virtual button commands, and mirrors firmware logs.
- A desktop “Virtual Controller” UI for development workflows.

The codebase is organized so each concern (hardware drivers, communication stacks, logging, debug tooling) remains isolated while flowing through a shared logging and state pipeline.

---

## Documentation

Project documentation is now generated with [Sphinx](https://www.sphinx-doc.org/).
Use the provided configuration under `docs/` to build HTML pages that include an
overview, hardware wiring guide, and API reference pulled directly from the
source docstrings.

```bash
pip install sphinx
sphinx-build -b html docs build/html
open build/html/index.html  # macOS; adjust for your platform
```

For CI or quick local validation, run the helper script alongside the deploy
utility:

```bash
python scripts/build_docs.py
```

The Sphinx site supersedes the long-form content that previously lived in this
README. The sections below keep a brief summary for quick discovery; see the
generated docs for the complete write-up.

---

## Top-Level Data Flow

```
Physical GPIO ┐
              ├─> InputManager ──> HIDController ──┬─> BLE (optional)
Virtual UI  ──┘                                    └─> USB HID (optional)
                                                   |
                                              DebugInterface
                                                   |
                                        Virtual Controller UI
```

1. **Inputs**  
   - Physical button presses (GPIO) are polled by `input_manager.InputManager`.
   - Virtual button presses (from the desktop UI) arrive via the serial `DEBUG` interface and are converted into the same `InputEvents` structure.

2. **HID Output**  
   - `hid_controller.HIDController` maintains active button sets, builds HID reports, and dispatches them to BLE and/or USB backends.

3. **Logging / Debugging**  
   - All modules log through `firmware_logging`.  
   - `debug_interface.DebugInterface` bridges these logs (and other state events) to the desktop UI.  
   - The UI requests its own logs by sending `LOG` commands so firmware is the single logging authority.

4. **Desktop UI**  
   - `tools/virtual_controller.py` renders the controller layout, mirrors firmware logs, injects virtual button presses, and tracks state updates.

---

## Modules & Responsibilities

### Firmware Modules

| Module | Responsibility |
| ------ | -------------- |
| `code.py` | Entry point: loads configuration, sets log level, instantiates all managers, runs the main loop. |
| `config.py` | Central configuration (button map, BLE/USB settings, debounce intervals, etc.). |
| `input_manager.py` | Polls GPIO inputs (wired as active-low with pull-ups by default) and emits debounced `InputEvents`. |
| `firmware_logging.py` | Minimal logging framework (levels, JSON serial output) used by every module. |
| `hid_controller.py` | Maintains controller state, maps logical buttons to HID report indices, dispatches to BLE/USB backends, notifies observers. |
| `ble_manager.py` | Encapsulates BLE radio setup, advertising, pairing, bond management, and event notifications. |
| `usb_hid_manager.py` | Manages optional mirroring of HID reports over USB. |
| `power_manager.py` | Stub placeholder for future power-management logic. |
| `debug_interface.py` | Serial bridge: parses commands (`PRESS`, `RELEASE`, `STATE?`, `PAIR`, `LOG`, `HELP`), mirrors logs via `DBG LOG`, broadcasts state snapshots. |

### Desktop Tooling

| Module | Responsibility |
| ------ | -------------- |
| `tools/virtual_controller.py` | Qt-based debug UI: serial bridge, virtual inputs, log viewer (filter/search/save/clear), BLE status reporting. Run with `--print-logs` to echo raw JSON to stdout. |
| `tests/` | Unit/integration tests (currently minimal) used to exercise host-side logic. |

### Hardware Pin Mapping

- `config.PIN_MAP` defines the association between logical buttons and physical GPIOs. Populate this dictionary with board pin objects (e.g. `board.D5`) or pin names (strings) before flashing the firmware.
- Buttons are assumed to be wired as **active-low** with pull-up resistors. `InputManager` enables `Pull.UP` on each configured pin and treats `value == False` as “pressed”.
- When a pin entry is `None`, that button is ignored during hardware polling (useful while wiring is in progress).

Current mapping (Adafruit Feather M4 Express):

| Button  | Pin |
|---------|-----|
| UP      | D5  |
| DOWN    | D6  |
| LEFT    | D9  |
| RIGHT   | D10 |
| A       | D11 |
| B       | D12 |
| X       | D13 |
| Y       | D0  |
| L1      | D1  |
| R1      | D4  |
| L2      | A0  |
| R2      | A1  |
| HOME    | A4  |
| START   | A2  |
| SELECT  | A3  |
| PAIRING | A5  |

> D5, D6, D9, D10, D11, D12, D13 are already soldered. Wire the remaining buttons to D0, D1, D4, A0, A1, A2, A3, A4, A5 as listed above.

---

## Logging Pipeline

1. Firmware modules use `firmware_logging.get_logger(name)` to emit messages.
2. `firmware_logging` prints each record to the serial console as a JSON line: `{"type": "log", "level": "...", "logger": "...", "message": "...", "timestamp": ...}`. Any connected host can parse these lines directly.
3. `debug_interface.DebugInterface` emits other structured events (state snapshots, readiness, BLE notifications, etc.) as JSON lines with `type` fields such as `ready`, `state`, `info`, `warn`.
4. The desktop UI watches the serial stream, parses every JSON object, reacts to `state` updates, and mirrors the raw JSON text in the log pane. By default the UI keeps these logs inside the window; launching with `--print-logs` also echoes each line to stdout.
5. When the UI needs to log something (e.g., “Connecting to …”), it sends `LOG <LEVEL> <LOGGER> <MESSAGE>`. The firmware re-emits that message through `firmware_logging`, so the entry appears for every listener.

---

## Serial Debug Protocol

Commands accepted by `debug_interface.DebugInterface`:

| Command | Description |
| ------- | ----------- |
| `PRESS <BUTTON>` | Simulate a button press (button name is case-insensitive, must match configured list). |
| `RELEASE <BUTTON>` | Simulate a button release. |
| `STATE?` | Request current active buttons; firmware responds with a `state` JSON snapshot. |
| `PAIR` | Force BLE pairing mode (clears bonds, restarts advertising). |
| `LOG <LEVEL> <LOGGER> <MESSAGE>` | Emit a log line (e.g., from the desktop UI). |
| `HELP` | Print command list and configured buttons. |

`DebugInterface` also pushes asynchronous messages:

- `READY` with the button list when the interface initializes.
- `STATE` whenever button state changes.
- `INFO/WARN/ERR` reports describing BLE events, serial connectivity, etc.
- `LOG` entries matching `DBG LOG` prints.

---

## Desktop UI (Virtual Controller)

Key components inside `tools/virtual_controller.py`:

| Component | Responsibility |
| --------- | -------------- |
| `SerialBridge` | Background thread + worker managing the serial connection so Qt stays responsive. |
| `DebuggerWindow` | Main window: builds the controller layout, log viewer, toolbar (filter/search/save/clear), and issues serial commands. |
| Filtering/Search | Logs are cached with their levels so the view can rebuild instantly when the filter changes. Search supports wrap-around navigation. |
| Logging | `_log_with_level` routes UI messages to firmware via `LOG` commands; the firmware’s echoed entries populate the UI (and stdout when `--print-logs` is supplied). |

---

## Current State & Roadmap

Completed / working:

- Modular logging infrastructure shared by firmware and UI.
- Serial debug bridge with virtual button injection.
- HID controller scaffolding for BLE/USB (USB path is stub-friendly).
- Desktop UI with log filtering/searching/saving.
- Command path for host-side logs to flow through firmware.

Planned next steps:

1. Finalize the hardware pin map and validate debouncing with the production wiring.
2. Flesh out BLE lifecycle handling, including connection state mirrored in the UI.
3. Expand automated tests for host tooling and, where possible, firmware logic.

---

## Development Notes

- The repo targets CircuitPython. The `lib/` folder includes the frozen dependencies (`adafruit_ble`, `adafruit_hid`, etc.).
- Desktop tooling depends on PySide6 (Qt for Python).
- Use `python -m py_compile ...` for quick syntax validation; run `python tools/virtual_controller.py --port <serial>` for the UI.
- When sending logs from the host, keep messages single-line (newlines are escaped as `\\n` by the UI before sending).

---

## Contributing

1. Ensure you have the required Python environment (PySide6 for the UI, CircuitPython SDK for firmware deployment).
2. Update or add unit tests if making substantial changes.
3. Keep modules focused: logging stays in `firmware_logging`, hardware access in managers, UI-specific tweaks in `tools/`.
4. Submit PRs with clear descriptions and testing notes.
