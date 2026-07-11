#!/usr/bin/env python3
"""Regenerate library/panel_devices.pretty from build_panel_device().

Run with a Python that can import pcbnew (KiCad's own, or a Linux system
install):    python3 scripts/gen_panel_library.py

The generated .kicad_mod files are committed, so end users never run this;
it exists so the starter library stays reproducible from one parametric
source of truth.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pcbnew  # noqa: E402
from kicad_plugin.panel_device_wizard import build_panel_device  # noqa: E402

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "library",
                                   "panel_devices.pretty"))

# name, width, height, top labels, bottom labels, extras
DEVICES = [
    ("Contactor_45x90",       45, 90, ["L1", "L2", "L3", "A1"],
                                       ["T1", "T2", "T3", "A2"], {}),
    ("Breaker_1P_18x90",      18, 90, ["1"], ["2"], {}),
    ("Breaker_2P_36x90",      36, 90, ["1", "3"], ["2", "4"], {}),
    ("PSU_24V_78x93",         78, 93, ["L", "N", "PE"],
                                       ["V+", "V+", "V-", "V-"],
     {"bottom_pitch_mm": 12.0}),
    ("Motor_3ph_TB_80x80",    80, 80, ["U", "V", "W", "PE"], [],
     {"top_pitch_mm": 15.0, "inset_mm": 12.0}),
    # feed-through terminal strip: same circuit top and bottom, so the pad
    # numbers repeat on both rows on purpose
    ("TerminalStrip_12x5mm",  62, 42, [str(i) for i in range(1, 13)],
                                       [str(i) for i in range(1, 13)],
     {"top_pitch_mm": 5.0, "bottom_pitch_mm": 5.0, "pad_mm": 2.5,
      "inset_mm": 6.0}),
]


def _saver():
    """KiCad 9/10: instantiate the s-expression IO directly (the path-based
    pcbnew.FootprintSave guesser returns no plugin for a new empty .pretty)."""
    for cls in ("PCB_IO_KICAD_SEXPR", "PCB_IO"):
        if hasattr(pcbnew, cls):
            return getattr(pcbnew, cls)()
    return None


def main():
    os.makedirs(LIB, exist_ok=True)
    io = _saver()
    board = pcbnew.BOARD()
    for name, w, h, top, bottom, extra in DEVICES:
        fp = pcbnew.FOOTPRINT(board)
        fp.SetFPID(pcbnew.LIB_ID("panel_devices", name))
        fp.SetValue(name)
        fp.SetReference("REF**")
        fp.SetAttributes(pcbnew.FP_SMD | pcbnew.FP_EXCLUDE_FROM_POS_FILES
                         | pcbnew.FP_BOARD_ONLY)
        build_panel_device(pcbnew, fp, width_mm=w, height_mm=h,
                           top_labels=top, bottom_labels=bottom, **extra)
        (io.FootprintSave if io is not None
         else pcbnew.FootprintSave)(LIB, fp)
        print(f"  {name}: {len(fp.Pads())} pads")
    print(f"library -> {os.path.normpath(LIB)}")


if __name__ == "__main__":
    main()
