"""Integration test against REAL pcbnew (KiCad 9/10) — no mocks.

Skips cleanly when pcbnew is absent (the mock-based suite covers that case) or
too old for the fixture's file format. In CI this runs in the job that installs
KiCad 10 from the official PPA; locally it runs wherever `python3 -c "import
pcbnew"` works headless.

The fixture (tests/fixtures/kicad10_panel/) is a real KiCad 10 project:
  * net classes 14AWG_BN (color swatch #996515, no width) and 16AWG_MOTOR
    (track width 1.31 mm, no color) — exercising the Has* gates both ways;
  * W5 group-bus nets (/W5.L1..L3) routed as L-shapes summing 15.7 mm each,
    the motor net routed at 49.442 mm, everything else unrouted;
  * harness_specs.yaml with defaults.gauge, classes, and a declared W5 cable —
    the exact configuration that exposed the precedence bug.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "kicad10_panel")

try:
    import pcbnew
except ImportError:
    pytest.skip(
        "pcbnew integration: pcbnew not importable (install KiCad)",
        allow_module_level=True,
    )

try:
    board = pcbnew.LoadBoard(os.path.join(FIXTURE, "Untitled.kicad_pcb"))
except Exception as e:
    pytest.skip(
        f"pcbnew integration: fixture not loadable by this KiCad "
        f"({pcbnew.GetBuildVersion()}): {e}",
        allow_module_level=True,
    )

from harness.ingest import KicadBoardSource  # noqa: E402
from kicad_plugin.core import generate_harness_docs  # noqa: E402


def test_board_adapter_reads_netclass_color_width_length():
    conn = KicadBoardSource.from_board(board, pcbnew).load()
    nets = {n.name: n for n in conn.nets}

    assert sorted(conn.components) == ["J1", "J2", "J3", "J4", "J5", "J6"]

    # composite class membership, exactly as KiCad reports it
    assert nets["/L1"].netclass == "14AWG_BN,Default"
    assert nets["Net-(J1-Pin_3)"].netclass == "16AWG_MOTOR,Default"

    # color swatch: set on 14AWG_BN only (Has* gate must hold it back elsewhere)
    assert nets["/L1"].color == "#996515", nets["/L1"].color
    assert nets["Net-(J1-Pin_3)"].color == ""
    assert nets["/W5.L1"].color == ""

    # track width: set on 16AWG_MOTOR only; Default's 0.2 mm must NOT leak in
    assert nets["Net-(J1-Pin_3)"].track_width_mm == 1.31
    assert nets["/L1"].track_width_mm is None
    assert nets["/W5.L1"].track_width_mm is None

    # routed length: summed per net; unrouted nets stay None
    for core in ("L1", "L2", "L3"):
        got = nets[f"/W5.{core}"].length_mm
        assert got is not None and abs(got - 15.7) < 0.01, got
    got = nets["Net-(J1-Pin_3)"].length_mm
    assert got is not None and abs(got - 49.442) < 0.01, got
    assert nets["/L1"].length_mm is None


def test_full_pipeline_csv(tmp_dir):
    res = generate_harness_docs(
        board, pcbnew_module=pcbnew,
        specs_path=os.path.join(FIXTURE, "harness_specs.yaml"),
        out_dir=tmp_dir, stem="it")
    assert res.wire_count == 9, res.wire_count
    assert not res.warnings, res.warnings

    import csv
    with open(os.path.join(tmp_dir, "it_wirelist.csv"), newline="") as fh:
        rows = {r["net"]: r for r in csv.DictReader(fh)}

    # cable gauge beats defaults.gauge (the live '20 AWG vs 1.5 mm2' regression)
    for core, color in (("L1", "BN"), ("L2", "BK"), ("L3", "GY")):
        r = rows[f"/W5.{core}"]
        assert r["gauge"] == "1.5 mm2", r["gauge"]
        assert r["color"] == color
        assert r["wire_no"] == f"W5-{core}"
        assert r["length_mm"] == "15.7"
        assert r["jacket"] == "PVC" and r["shield"] == "yes"

    # board track width beats defaults.gauge ('leave it unset -> take from board')
    motor = rows["Net-(J1-Pin_3)"]
    assert motor["gauge"] == "1.31 mm", motor["gauge"]
    assert motor["length_mm"] == "49.4"

    # explicit class gauge/color beat board color swatch; unrouted -> blank length
    r = rows["/L1"]
    assert r["gauge"] == "14 AWG" and r["color"] == "BN"
    assert r["length_mm"] == ""

    # WireViz YAML emitted too (PyYAML is present alongside real KiCad here)
    assert any(p.endswith("it_harness.yaml") for p in res.outputs), res.outputs

    # panel wiring diagram emitted and well-formed, with wire colors + labels
    svg_path = os.path.join(tmp_dir, "it_panel.svg")
    assert any(p.endswith("it_panel.svg") for p in res.outputs), res.outputs
    import xml.etree.ElementTree as ET
    svg = open(svg_path).read()
    ET.fromstring(svg)
    assert ">W5-L1<" in svg          # wire-number flag from the routed cable
    assert "#7B3F00" in svg          # BN core rendered in IEC brown

    # wire numbers persisted next to the outputs; a rerun is byte-identical
    assert any(p.endswith("wire_numbers.json") for p in res.outputs), res.outputs
    csv1 = open(os.path.join(tmp_dir, "it_wirelist.csv")).read()
    generate_harness_docs(board, pcbnew_module=pcbnew,
                          specs_path=os.path.join(FIXTURE, "harness_specs.yaml"),
                          out_dir=tmp_dir, stem="it")
    assert open(os.path.join(tmp_dir, "it_wirelist.csv")).read() == csv1


def test_load_geometry():
    geo = KicadBoardSource.from_board(board, pcbnew).load_geometry()
    assert sorted(geo.footprints) == ["J1", "J2", "J3", "J4", "J5", "J6"]
    j1 = geo.footprints["J1"]
    assert j1.outlines, "expected fab/silk outline polylines"
    assert "1" in j1.pads and len(j1.pads["1"]) == 3
    # 7 routed segments: 3 W5 cores x 2 (L-shapes) + 1 straight motor run
    assert len(geo.tracks) == 7, len(geo.tracks)
    nets = {t[0] for t in geo.tracks}
    assert nets == {"/W5.L1", "/W5.L2", "/W5.L3", "Net-(J1-Pin_3)"}
    widths = {round(t[3], 2) for t in geo.tracks}
    assert widths == {0.25}, widths


def test_netlist_route_carries_classes(tmp_dir):
    """kicad-cli exports class="X,Default" per net; the CLI route must use it."""
    import shutil
    import subprocess
    kicad_cli = shutil.which("kicad-cli")
    if not kicad_cli:
        print("  (kicad-cli not found; netlist-route check skipped)")
        return
    xml = os.path.join(tmp_dir, "it.net.xml")
    subprocess.run([kicad_cli, "sch", "export", "netlist", "--format", "kicadxml",
                    "-o", xml, os.path.join(FIXTURE, "Untitled.kicad_sch")],
                   check=True, capture_output=True)
    from harness.ingest import KicadNetlistSource
    conn = KicadNetlistSource(xml).load()
    nets = {n.name: n for n in conn.nets}
    assert nets["/L1"].netclass == "14AWG_BN,Default", nets["/L1"].netclass


if __name__ == "__main__":
    import tempfile
    test_board_adapter_reads_netclass_color_width_length()
    test_load_geometry()
    with tempfile.TemporaryDirectory() as td:
        test_full_pipeline_csv(td)
    with tempfile.TemporaryDirectory() as td:
        test_netlist_route_carries_classes(td)
    print(f"OK pcbnew integration on {pcbnew.GetBuildVersion()}: "
          f"netclass color/width + routed lengths -> CSV")
