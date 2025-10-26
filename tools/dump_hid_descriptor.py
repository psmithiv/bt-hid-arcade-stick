#!/usr/bin/env python3
"""
Dump the HID report descriptor macOS sees for the arcade stick.

This script shells out to ``ioreg`` (macOS only) and extracts the hex report
descriptor exposed by the IOUSB/IOHID nodes whose name matches ``--device``.
Use it to confirm that the host is seeing the 16-button descriptor from
``sd/boot.py`` after redeploying the firmware.

Example:

    python tools/dump_hid_descriptor.py --device \"Feather M4 Express\"
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from textwrap import wrap

REPORT_RE = re.compile(r'"ReportDescriptor"\s*=\s*<([0-9a-fA-F]+)>')
KEY_VALUE_RE = re.compile(r'^\s*"([^"]+)"\s*=\s*(.+)$')


def _run_ioreg(device_name: str) -> list[str]:
    cmd = ["ioreg", "-n", device_name, "-r", "-l", "-w0"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        sys.exit("This script must be run on macOS (ioreg missing).")
    except subprocess.CalledProcessError as exc:  # pragma: no cover - host diagnostics
        sys.exit(f"ioreg failed: {exc.stderr or exc}")

    lines = result.stdout.splitlines()
    if not lines:
        sys.exit(f"No IORegistry nodes matched '{device_name}'. Try a different --device value.")
    return lines


def _parse_properties(lines: list[str]) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        stripped = stripped.lstrip("| ")
        match = KEY_VALUE_RE.match(stripped)
        if not match:
            continue
        key, value = match.groups()
        props.setdefault(key, value.strip())
    return props


def _decode_report(data: str) -> bytes:
    return bytes.fromhex(data)


def main():
    parser = argparse.ArgumentParser(description="Dump macOS HID report descriptors for the arcade stick.")
    parser.add_argument(
        "--device",
        default="Feather M4 Express",
        help="Exact IORegistry name to inspect (default: %(default)s).",
    )
    args = parser.parse_args()

    lines = _run_ioreg(args.device)
    descriptors = []

    for line in lines:
        match = REPORT_RE.search(line)
        if match:
            descriptors.append(match.group(1))

    if not descriptors:
        sys.exit(
            "No report descriptors were found. If you recently changed PRODUCT in boot.py, "
            "pass that exact string via --device."
        )

    props = _parse_properties(lines)
    vendor = props.get("VendorID", "<unknown>")
    product_id = props.get("ProductID", "<unknown>")
    max_input = props.get("MaxInputReportSize", "<unknown>")
    product_name = props.get("Product", args.device)
    manufacturer = props.get("Manufacturer", "<unknown>")

    print(f"Device: {product_name} by {manufacturer}")
    print(f"  VendorID={vendor} ProductID={product_id}")
    print(f"  MaxInputReportSize={max_input} bytes")

    for idx, hex_blob in enumerate(descriptors, start=1):
        data = _decode_report(hex_blob)
        print(f"\nDescriptor #{idx}: {len(data)} bytes")
        for chunk in wrap(hex_blob, 32):
            bytes_str = " ".join(chunk[i : i + 2] for i in range(0, len(chunk), 2))
            print(f"  {bytes_str}")


if __name__ == "__main__":
    main()
