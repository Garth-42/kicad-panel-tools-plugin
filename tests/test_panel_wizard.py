"""Panel-device footprint wizard: pure-python label logic always; builder +
starter library against real pcbnew when available (skips cleanly otherwise)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kicad_plugin.panel_device_wizard import _split_labels  # noqa: E402

LIB = os.path.join(os.path.dirname(__file__), "..", "library",
                   "panel_devices.pretty")


def test_split_labels():
    assert _split_labels("L1, L2 ,L3", 99) == ["L1", "L2", "L3"]
    assert _split_labels("", 3) == ["1", "2", "3"]
    assert _split_labels("", 2, start=4) == ["4", "5"]
    assert _split_labels(None, 0) == []


def test_builder_and_library_with_pcbnew():
    try:
        import pcbnew
    except ImportError:
        print("SKIP wizard builder: pcbnew not importable")
        return False

    from kicad_plugin.panel_device_wizard import build_panel_device
    fp = pcbnew.FOOTPRINT(pcbnew.BOARD())
    build_panel_device(pcbnew, fp, width_mm=45, height_mm=90,
                       top_labels=["L1", "L2", "L3"],
                       bottom_labels=["T1", "T2", "T3"],
                       top_pitch_mm=10, bottom_pitch_mm=10, inset_mm=5)
    pads = {p.GetNumber(): p.GetPosition() for p in fp.Pads()}
    assert sorted(pads) == ["L1", "L2", "L3", "T1", "T2", "T3"]
    # top row 5mm below the top edge (y = -45+5 = -40mm), 10mm pitch centered
    assert pcbnew.ToMM(pads["L1"].y) == -40.0
    assert pcbnew.ToMM(pads["L2"].x) - pcbnew.ToMM(pads["L1"].x) == 10.0
    assert pcbnew.ToMM(pads["T2"].y) == 40.0
    # outline on F.Fab + silk
    layers = {g.GetLayer() for g in fp.GraphicalItems()}
    assert pcbnew.F_Fab in layers and pcbnew.F_SilkS in layers

    # every committed starter footprint reloads with pads
    io = pcbnew.PCB_IO_KICAD_SEXPR()
    names = [f[:-len(".kicad_mod")] for f in sorted(os.listdir(LIB))
             if f.endswith(".kicad_mod")]
    assert len(names) >= 6, names
    for name in names:
        lfp = io.FootprintLoad(LIB, name)
        assert lfp is not None and len(lfp.Pads()) >= 1, name
    return True


if __name__ == "__main__":
    test_split_labels()
    ran = test_builder_and_library_with_pcbnew()
    print("OK panel wizard: labels%s" %
          (" + builder geometry + starter library (real pcbnew)" if ran else
           " (pcbnew checks skipped)"))
