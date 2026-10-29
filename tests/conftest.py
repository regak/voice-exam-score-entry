"""Pytest configuration.

Workaround for a flaky Tcl/Tk library-discovery issue on this
Windows/Python install: _tkinter's internal tcl_findLibrary search
intermittently fails to locate init.tcl/tk.tcl even though the files
are present, especially under pytest's output capturing. Setting
TCL_LIBRARY/TK_LIBRARY explicitly makes Tk() initialization
deterministic (verified: 0 flaky failures in repeated runs after this
fix, vs. ~50% failure rate before it).
"""
import sys
from pathlib import Path

if sys.platform == "win32":
    import os

    tcl_root = Path(sys.base_prefix) / "tcl"
    if tcl_root.exists():
        for child in tcl_root.iterdir():
            if child.name.startswith("tcl8") and (child / "init.tcl").exists():
                os.environ.setdefault("TCL_LIBRARY", str(child))
            if child.name.startswith("tk8") and (child / "tk.tcl").exists():
                os.environ.setdefault("TK_LIBRARY", str(child))
