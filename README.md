# Bluetooth HID Arcade Stick Firmware

This project is a CircuitPython-based firmware and companion desktop tooling for a Bluetooth / USB arcade stick. It provides:

- A modular firmware that maps physical inputs to Bluetooth Low Energy (BLE) and USB HID reports.
- A serial debug interface that exposes state, accepts virtual button commands, and mirrors firmware logs.
- A desktop “Virtual Controller” UI for development workflows.

The codebase is organized so each concern (hardware drivers, communication stacks, logging, debug tooling) remains isolated while flowing through a shared logging and state pipeline.

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
| `firmware_logging.py` | Minimal logging framework (levels, sinks, formatters) used by every module. |
| `input_manager.py` | Polls GPIO inputs (placeholder in current HEAD) and emits debounced `InputEvents`. |
| `hid_controller.py` | Maintains controller state, maps logical buttons to HID report indices, dispatches to BLE/USB backends, notifies observers. |
| `ble_manager.py` | Encapsulates BLE radio setup, advertising, pairing, bond management, and event notifications. |
| `usb_hid_manager.py` | Manages optional mirroring of HID reports over USB. |
| `power_manager.py` | Stub placeholder for future power-management logic. |
| `debug_interface.py` | Serial bridge: parses commands (`PRESS`, `RELEASE`, `STATE?`, `PAIR`, `LOG`, `HELP`), mirrors logs via `DBG LOG`, broadcasts state snapshots. |

### Desktop Tooling

| Module | Responsibility |
| ------ | -------------- |
| `tools/virtual_controller.py` | Qt-based debug UI: serial bridge, virtual inputs, log viewer (filter/search/save/clear), BLE status reporting. |
| `tests/` | Unit/integration tests (currently minimal) used to exercise host-side logic. |

---

## Logging Pipeline

1. All firmware modules use `firmware_logging.get_logger(name)` to emit messages.
2. `debug_interface.DebugInterface` installs a logging sink so each message is printed in the console as `DBG LOG {...}` and forwarded to any existing sink.
3. The desktop UI listens for `DBG LOG` lines, decodes JSON payloads, and styles/logs them locally.
4. When the UI wants to log something (e.g., “Connecting to …”), it sends a `LOG <LEVEL> <LOGGER> <MESSAGE>` command over serial. The firmware receives it in `_handle_host_log`, emits the log via the same logger, and the message is mirrored back through the standard path.  
   This keeps firmware as the single source of truth for diagnostics.

---

## Serial Debug Protocol

Commands accepted by `debug_interface.DebugInterface`:

| Command | Description |
| ------- | ----------- |
| `PRESS <BUTTON>` | Simulate a button press (button name is case-insensitive, must match configured list). |
| `RELEASE <BUTTON>` | Simulate a button release. |
| `STATE?` | Request current active buttons; firmware responds with a `DBG STATE` JSON snapshot. |
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
| Logging | `_log_with_level` routes UI messages to firmware via `LOG` command; `DBG LOG` echoes are deduplicated against pending entries to avoid duplicates. |

---

## Current State & Roadmap

Completed / working:

- Modular logging infrastructure shared by firmware and UI.
- Serial debug bridge with virtual button injection.
- HID controller scaffolding for BLE/USB (USB path is stub-friendly).
- Desktop UI with log filtering/searching/saving.
- Command path for host-side logs to flow through firmware.

Planned next steps:

1. Integrate actual GPIO polling in `InputManager` so physical buttons feed into `HIDController`.
2. Reflect physical button activity in the desktop UI (leveraging existing `STATE` events).
3. Finish BLE lifecycle handling, including connection state mirrored in the UI.
4. Expand automated tests for host tooling and, where possible, firmware logic.

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

