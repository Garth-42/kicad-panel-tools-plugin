"""Render the emitted YAML through REAL WireViz (needs `wireviz` + graphviz).

Skips cleanly when either is missing; CI runs it in a dedicated job. This is
the check that caught a real bug: WireViz coerces numeric-looking connection
pin refs to int while connector `pins` stay as authored, so emitting '1' as a
string on both sides failed with "J1:1 not found". The mock board exercises
numeric pins (1,2,3), alpha pins (U, V, A1) and a dashed designator (-M1).
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tests.mock_pcbnew as mock  # noqa: E402
from harness.ingest import KicadBoardSource  # noqa: E402
from harness.specs import SpecStore  # noqa: E402
from harness.engine import build_harness  # noqa: E402
from harness.emit import write_wireviz  # noqa: E402
from harness.emit.wireviz_yaml import build_wireviz  # noqa: E402


def _harness():
    conn = KicadBoardSource.from_board(mock.sample_board(),
                                       pcbnew_module=mock).load()
    specs = SpecStore(classes={
        "14AWG_BN": {"cable": "W1", "gauge": "14 AWG", "color": "BN"},
        "14AWG_BK": {"cable": "W1", "gauge": "14 AWG", "color": "BK"},
        "18AWG_BU": {"cable": "W2", "gauge": "18 AWG", "color": "BU"},
    })
    h, _ = build_harness(conn, specs)
    return h, conn


def test_pin_ids_match_wireviz_coercion():
    # Numeric pins must be ints on both sides; alpha pins stay strings.
    h, conn = _harness()
    wv = build_wireviz(h, components=conn.components)
    assert wv["connectors"]["X1"]["pins"] == [1, 2, 3]
    assert "U" in wv["connectors"]["-M1"]["pins"]
    for cs in wv["connections"]:
        for end in (cs[0], cs[2]):
            (pin,) = next(iter(end.values()))
            assert not (isinstance(pin, str) and pin.isdigit()), \
                f"numeric pin emitted as string: {end}"


def test_render_with_real_wireviz():
    wireviz = shutil.which("wireviz")
    dot = shutil.which("dot")
    if not wireviz or not dot:
        missing = [n for n, p in (("wireviz", wireviz), ("graphviz/dot", dot))
                   if not p]
        print(f"SKIP wireviz render: {', '.join(missing)} not installed")
        return False

    h, conn = _harness()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "h.yaml")
        write_wireviz(h, path, components=conn.components)
        proc = subprocess.run([wireviz, path], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        for ext in (".png", ".svg", ".html", ".bom.tsv"):
            out = os.path.join(td, "h" + ext)
            assert os.path.exists(out) and os.path.getsize(out) > 0, out
        bom = open(os.path.join(td, "h.bom.tsv")).read()
        assert "ABB-M3" in bom, "footprint MPN missing from WireViz BOM"
    return True


def test_render_extends_path_with_tool_dirs():
    # GUI-launched KiCad on macOS/Windows gets a minimal PATH; render_wireviz
    # must splice in the known install prefixes (Homebrew etc.) so wireviz/dot
    # are found both by us and by the subprocesses WireViz spawns itself.
    import harness.wireviz as hw
    old_dirs, old_path = hw._EXTRA_TOOL_DIRS, os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory() as td:
        try:
            hw._EXTRA_TOOL_DIRS = (td,)
            hw._extend_path_for_tools()
            assert td in os.environ["PATH"].split(os.pathsep)
            hw._extend_path_for_tools()  # idempotent: no duplicate entry
            assert os.environ["PATH"].split(os.pathsep).count(td) == 1
            hw._EXTRA_TOOL_DIRS = (os.path.join(td, "missing"),)
            hw._extend_path_for_tools()  # nonexistent dirs are not added
            assert os.path.join(td, "missing") not in os.environ["PATH"]
        finally:
            hw._EXTRA_TOOL_DIRS = old_dirs
            os.environ["PATH"] = old_path


if __name__ == "__main__":
    test_pin_ids_match_wireviz_coercion()
    test_render_extends_path_with_tool_dirs()
    print("OK render PATH extension: tool dirs spliced in, idempotent")
    rendered = test_render_with_real_wireviz()
    if rendered:
        print("OK wireviz render: png/svg/html/BOM produced, MPN in BOM")
    else:
        print("OK wireviz yaml structure (render skipped)")


def test_vendored_wireviz_renderer_outputs_or_cleanly_requires_graphviz():
    h, conn = _harness()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "h.yaml")
        write_wireviz(h, path, components=conn.components)
        from harness.wireviz import render_wireviz
        old_path = os.environ.get("PATH", "")
        try:
            # Hide a system wireviz executable so this exercises the vendored path.
            os.environ["PATH"] = os.pathsep.join(
                p for p in old_path.split(os.pathsep)
                if not os.path.exists(os.path.join(p, "wireviz"))
            )
            if not shutil.which("dot"):
                try:
                    render_wireviz(path)
                except RuntimeError as e:
                    assert "Graphviz" in str(e) or "dot" in str(e)
                else:
                    raise AssertionError("render should require graphviz/dot")
                return
            outs = render_wireviz(path)
        finally:
            os.environ["PATH"] = old_path
        assert {os.path.splitext(p)[1] for p in outs} >= {".png", ".svg", ".html", ".tsv"}
        for out in outs:
            assert os.path.exists(out) and os.path.getsize(out) > 0, out
        assert "ABB-M3" in open(os.path.join(td, "h.bom.tsv"), encoding="utf-8").read()
