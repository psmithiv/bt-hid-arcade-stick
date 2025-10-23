"""Sphinx configuration for the Bluetooth HID Arcade Stick project."""

from __future__ import annotations

import os
import sys
from datetime import datetime

# Ensure the project root is importable when autodoc runs.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# -- Project information -----------------------------------------------------

project = "Bluetooth HID Arcade Stick"
author = "Paul Smith IV"
copyright = f"{datetime.now():%Y}, {author}"


# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

autodoc_member_order = "bysource"
autodoc_typehints = "description"
napoleon_google_docstring = False
napoleon_numpy_docstring = False
autodoc_mock_imports = [
    "PySide6",
    "serial",
    "usb_hid",
    "adafruit_ble",
    "digitalio",
    "board",
    "supervisor",
]

templates_path = ["_templates"]
exclude_patterns: list[str] = []


# -- Options for HTML output -------------------------------------------------

html_theme = "alabaster"
html_static_path = ["_static"]
