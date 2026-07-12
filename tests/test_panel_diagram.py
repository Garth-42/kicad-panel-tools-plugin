"""Panel wiring-diagram SVG emitter: pure-data tests (no KiCad needed)."""
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from harness.model import (Connectivity, Net, Node,  # noqa: E402
                           BoardGeometry, FootprintGeometry)
from harness.specs import SpecStore  # noqa: E402
from harness.engine import build_harness  # noqa: E402
from harness.emit.panel_diagram_svg import build_panel_svg, _wire_color  # noqa: E402


def _fixture():
    conn = Connectivity(nets=[
        Net(code="1", name="/L1", nodes=[Node("K1", "L1"), Node("X1", "1")],
            netclass="14AWG_BN"),
        Net(code="2", name="/PE", nodes=[Node("K1", "A2"), Node("X1", "2")],
            netclass="PE_GNYE"),
    ])
    specs = SpecStore(classes={"14AWG_BN": {"gauge": "14 AWG", "color": "BN"},
                               "PE_GNYE": {"color": "GNYE"}},
                      nets={"/L1": {"wire_no": "101"}})
    harness, _ = build_harness(conn, specs)

    geo = BoardGeometry(
        footprints={
            "K1": FootprintGeometry(ref="K1", x=50, y=50,
                                    outlines=[[(30, 20), (70, 20), (70, 80),
                                               (30, 80), (30, 20)]],
                                    pads={"L1": (40, 25, 4.0),
                                          "A2": (60, 25, 4.0)}),
            "X1": FootprintGeometry(ref="X1", x=150, y=50,
                                    outlines=[[(140, 40), (160, 40),
                                               (160, 60), (140, 60),
                                               (140, 40)]],
                                    pads={"1": (145, 45, 3.0),
                                          "2": (155, 45, 3.0)}),
        },
        tracks=[("/L1", (40, 25), (145, 45), 1.6),
                ("/PE", (60, 25), (155, 45), 1.6)],
        edges=[[(0, 0), (200, 0), (200, 100), (0, 100), (0, 0)]],
        title={"title": "Demo panel", "rev": "B"},
    )
    return harness, geo


def test_svg_structure_and_content():
    harness, geo = _fixture()
    svg = build_panel_svg(harness, geo)
    root = ET.fromstring(svg)                       # valid XML
    assert root.tag.endswith("svg")

    assert "#7B3F00" in svg                          # BN wire color
    assert 'stroke-dasharray' in svg                 # GNYE stripe overlay
    assert ">101<" in svg                            # explicit wire number flag
    assert ">K1<" in svg and ">X1<" in svg           # ref labels
    assert ">L1<" in svg and ">A2<" in svg           # terminal labels
    assert "Demo panel" in svg and "rev B" in svg    # title block
    # viewBox derived from the panel edge (0..200 x 0..100, plus margin)
    vb = [float(v) for v in root.get("viewBox").split()]
    assert vb[0] < 0 and vb[2] > 200


def test_flag_deconfliction():
    # ten parallel wires sharing a midpoint: all ten labels must be placed,
    # pairwise at least ~3mm apart
    nets, tracks = [], []
    for i in range(10):
        name = f"/W{i}"
        nets.append(Net(code=str(i), name=name,
                        nodes=[Node("A", str(i)), Node("B", str(i))]))
        tracks.append((name, (0.0, i * 2.0), (100.0, i * 2.0), 1.0))
    harness, _ = build_harness(Connectivity(nets=nets), SpecStore())
    svg = build_panel_svg(harness, BoardGeometry(tracks=tracks))
    root = ET.fromstring(svg)
    ns = "{http://www.w3.org/2000/svg}"
    flags = [t for t in root.iter(f"{ns}text")
             if t.get("text-anchor") == "middle" and t.get("stroke")]
    labels = [t for t in flags if (t.text or "").isdigit()]
    assert len(labels) == 10, len(labels)
    pos = [(float(t.get("x")), float(t.get("y"))) for t in labels]
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            d2 = ((pos[i][0] - pos[j][0]) ** 2 + (pos[i][1] - pos[j][1]) ** 2)
            assert d2 >= 2.8 ** 2, (pos[i], pos[j])


def test_wire_color_mapping():
    assert _wire_color("BN") == ("#7B3F00", None)
    assert _wire_color("#123456") == ("#123456", None)
    assert _wire_color("GNYE")[1] is not None        # striped
    assert _wire_color("")[0] == "#606060"           # fallback
    assert _wire_color("nonsense")[0] == "#606060"


def test_empty_geometry_is_still_valid_svg():
    harness, _ = _fixture()
    svg = build_panel_svg(harness, BoardGeometry())
    ET.fromstring(svg)


if __name__ == "__main__":
    test_svg_structure_and_content()
    test_flag_deconfliction()
    test_wire_color_mapping()
    test_empty_geometry_is_still_valid_svg()
    print("OK panel diagram: structure, colors, GNYE stripe, flag "
          "de-confliction, title block")
