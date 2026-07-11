"""Lock in the spec precedence ladder (see engine.py docstring).

    nets: > cores > classes/cable-level > board-derived > defaults

Every case here was a real failure mode: `defaults` used to be applied first,
so it masked cable-level gauge and board-derived values (seen live as W5 cores
reporting '20 AWG' instead of the declared '1.5 mm2'), and per-core values used
to clobber per-net overrides.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from harness.model import Connectivity, Net, Node  # noqa: E402
from harness.specs import SpecStore  # noqa: E402
from harness.engine import build_harness  # noqa: E402


def _net(name, netclass="", **kw):
    return Net(code="1", name=name,
               nodes=[Node("J1", "1"), Node("J2", "1")], netclass=netclass, **kw)


def _one_wire(net, specs):
    harness, _ = build_harness(Connectivity(nets=[net]), specs, auto_number=False)
    assert len(harness.wires) == 1
    return harness.wires[0]


def test_cable_gauge_beats_defaults():
    # The live W5 bug: cables.W5.gauge must fill cores even with a default set.
    specs = SpecStore(defaults={"gauge": "20 AWG"},
                      cables={"W5": {"gauge": "1.5 mm2",
                                     "cores": {"L1": {"color": "BN"}}}})
    w = _one_wire(_net("/W5.L1"), specs)
    assert w.spec.gauge == "1.5 mm2", w.spec.gauge
    assert w.spec.color == "BN"
    assert w.spec.wire_no == "W5-L1"


def test_board_values_beat_defaults():
    # classes entry leaves gauge unset intending "take from board"; the global
    # default must not mask the board's track width (or its color swatch).
    specs = SpecStore(defaults={"gauge": "20 AWG", "color": "WH"},
                      classes={"16AWG_MOTOR": {"cable": "WM", "prefix": "M"}})
    w = _one_wire(_net("/M_U", "16AWG_MOTOR,Default",
                       track_width_mm=1.31, color="#996515"), specs)
    assert w.spec.gauge == "1.31 mm", w.spec.gauge
    assert w.spec.color == "#996515", w.spec.color


def test_class_values_beat_board():
    # Explicit YAML always beats derived board values.
    specs = SpecStore(classes={"14AWG_BN": {"gauge": "14 AWG", "color": "BN"}})
    w = _one_wire(_net("/L1", "14AWG_BN,Default",
                       track_width_mm=0.2, color="#123456"), specs)
    assert w.spec.gauge == "14 AWG"
    assert w.spec.color == "BN"


def test_cable_gauge_beats_board_width():
    # A declared cable gauge is explicit YAML; the Default class track width
    # (or any board width) must not override it.
    specs = SpecStore(cables={"W5": {"gauge": "1.5 mm2",
                                     "cores": {"L1": {}}}})
    w = _one_wire(_net("/W5.L1", "Default", track_width_mm=0.2), specs)
    assert w.spec.gauge == "1.5 mm2", w.spec.gauge


def test_nets_override_beats_cores():
    # nets: is the single highest layer -- including over per-core values.
    specs = SpecStore(cables={"W5": {"cores": {"L1": {"color": "BN"}}}},
                      nets={"/W5.L1": {"color": "RD", "wire_no": "201"}})
    w = _one_wire(_net("/W5.L1"), specs)
    assert w.spec.color == "RD", w.spec.color
    assert w.spec.wire_no == "201"      # explicit wire_no beats intrinsic W5-L1


def test_cores_beat_cable_level_and_classes():
    specs = SpecStore(classes={"CLS": {"color": "WH"}},
                      cables={"W5": {"color": "GY",
                                     "cores": {"L1": {"color": "BK"}}}})
    w = _one_wire(_net("/W5.L1", "CLS"), specs)
    assert w.spec.color == "BK", w.spec.color


def test_extras_precedence_and_defaults_passthrough():
    specs = SpecStore(defaults={"insulation": "PVC", "voltage": "300 V"},
                      classes={"CLS": {"insulation": "PTFE"}},
                      cables={"W5": {"shield": "yes",
                                     "cores": {"L1": {"shield": "foil"}}}},
                      nets={"/W5.L1": {"voltage": "600 V"}})
    w = _one_wire(_net("/W5.L1", "CLS"), specs)
    assert w.spec.extra["insulation"] == "PTFE"   # class beats default
    assert w.spec.extra["shield"] == "foil"       # core beats cable level
    assert w.spec.extra["voltage"] == "600 V"     # net beats default


def test_star_net_gets_no_board_length():
    # A routed length spans the whole net; stamping it on every star leg would
    # overstate each cut length, so legs stay blank (and the warning says so).
    net = Net(code="1", name="/GND",
              nodes=[Node("J1", "1"), Node("J2", "1"), Node("J3", "1")],
              length_mm=900.0)
    harness, warns = build_harness(Connectivity(nets=[net]), SpecStore(),
                                   auto_number=False)
    assert len(harness.wires) == 2
    assert all(w.spec.length_mm == "" for w in harness.wires)
    assert any("per-leg length left blank" in w for w in warns), warns

    # ...but an explicit nets: length still applies to every leg.
    specs = SpecStore(nets={"/GND": {"length_mm": "250"}})
    harness, _ = build_harness(Connectivity(nets=[net]), specs, auto_number=False)
    assert all(w.spec.length_mm == "250" for w in harness.wires)


def test_two_node_net_still_gets_board_length():
    w = _one_wire(_net("/SIG", length_mm=320.04), SpecStore())
    assert w.spec.length_mm == "320.0"


if __name__ == "__main__":
    test_cable_gauge_beats_defaults()
    test_board_values_beat_defaults()
    test_class_values_beat_board()
    test_cable_gauge_beats_board_width()
    test_nets_override_beats_cores()
    test_cores_beat_cable_level_and_classes()
    test_extras_precedence_and_defaults_passthrough()
    test_star_net_gets_no_board_length()
    test_two_node_net_still_gets_board_length()
    print("OK precedence ladder: nets > cores > classes/cable > board > defaults")
