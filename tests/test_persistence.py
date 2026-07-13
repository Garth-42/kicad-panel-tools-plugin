"""Wire-number persistence: numbers stay attached to the same wire across
re-exports, regardless of the ingest source's net iteration order (which was
observed to differ between machines for the same board)."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from harness.model import Connectivity, Net, Node  # noqa: E402
from harness.specs import SpecStore  # noqa: E402
from harness.engine import build_harness  # noqa: E402
from harness.numbering import GroupPrefix, GlobalSequence  # noqa: E402
from harness.persist import (WireNumberStore, collect_numbers,  # noqa: E402
                             legacy_keys, wire_key, WIRE_NUMBERS_NAME)


def _net(name, netclass="", nodes=None):
    # distinct pins per net: in a real design a pad belongs to exactly one
    # net, and endpoint-pair wire keys rely on that
    pin = name.lstrip("/")
    return Net(code="1", name=name,
               nodes=nodes or [Node("J1", pin), Node("J2", pin)],
               netclass=netclass)


SPECS = SpecStore(classes={"CLS": {"prefix": "M"}})


def _numbers(nets, known=None):
    h, _ = build_harness(Connectivity(nets=nets), SPECS,
                         numberer=GroupPrefix(), known_numbers=known)
    return {w.net: w.spec.wire_no for w in h.wires}, h


def test_numbers_survive_reordered_ingest():
    # First run establishes numbers; a rerun with nets in a different order
    # (as seen across machines) must keep every net -> number pairing.
    a, b, c = (_net("/A", "CLS"), _net("/B", "CLS"), _net("/C", "CLS"))
    first, h = _numbers([a, b, c])
    known = collect_numbers(h)
    second, _ = _numbers([c, a, b], known)
    assert second == first, (first, second)


def test_fresh_run_is_deterministic_without_store():
    # Even with no store, assignment iterates sorted wires, so two machines
    # with different net iteration orders agree on first-run numbers too.
    one, _ = _numbers([_net("/A", "CLS"), _net("/B", "CLS")])
    two, _ = _numbers([_net("/B", "CLS"), _net("/A", "CLS")])
    assert one == two == {"/A": "M-001", "/B": "M-002"}


def test_new_net_gets_unused_number():
    # A net added later must not steal a persisted number.
    first, h = _numbers([_net("/A", "CLS"), _net("/B", "CLS")])
    known = collect_numbers(h)                       # M-001, M-002
    nums, _ = _numbers([_net("/ZZ_NEW", "CLS"), _net("/A", "CLS"),
                        _net("/B", "CLS")], known)
    assert nums["/A"] == first["/A"] and nums["/B"] == first["/B"]
    assert nums["/ZZ_NEW"] == "M-003", nums


def test_explicit_and_intrinsic_numbers_beat_store():
    specs = SpecStore(nets={"/A": {"wire_no": "700"}},
                      cables={"W5": {"cores": {"L1": {}}}})
    known = {"/A": "OLD", "/W5.L1": "OLD"}
    h, _ = build_harness(Connectivity(nets=[_net("/A"), _net("/W5.L1")]),
                         specs, numberer=GlobalSequence(), known_numbers=known)
    got = {w.net: w.spec.wire_no for w in h.wires}
    assert got == {"/A": "700", "/W5.L1": "W5-L1"}, got


def test_star_legs_have_stable_keys():
    # >2-endpoint nets: nodes are sorted, so hub choice and per-leg keys don't
    # depend on pad iteration order.
    nodes = [Node("J3", "1"), Node("J1", "1"), Node("J2", "1")]
    h1, _ = build_harness(Connectivity(nets=[_net("/GND", nodes=nodes)]),
                          SpecStore(), numberer=GlobalSequence())
    h2, _ = build_harness(Connectivity(nets=[_net("/GND", nodes=nodes[::-1])]),
                          SpecStore(), numberer=GlobalSequence())
    assert collect_numbers(h1) == collect_numbers(h2)
    assert set(collect_numbers(h1)) == {"J1:1<->J2:1", "J1:1<->J3:1"}
    # a key is the sorted endpoint pair — never a net name, so renaming a net
    # ("Apply wire numbers to net names") or a schematic re-sync can't orphan it
    assert wire_key(Node("X1", "1"), Node("-M1", "U")) == \
        wire_key(Node("-M1", "U"), Node("X1", "1")) == "-M1:U<->X1:1"


def test_legacy_net_name_keys_still_apply_and_migrate():
    # A store written before the endpoint-key change (net-name keys) must keep
    # numbering the same wires; once saved, entries move to endpoint keys and
    # the superseded legacy entries are dropped — but legacy entries for wires
    # absent from this run survive (a returning wire gets its number back).
    legacy_store = {"/A": "M-007",                       # 2-endpoint net key
                    "/GND@J2:1": "M-008",                # star-leg key
                    "/GONE": "M-009"}                    # wire not in this run
    gnd = _net("/GND", "CLS", nodes=[Node("J1", "1"), Node("J2", "1"),
                                     Node("J3", "1")])
    h, _ = build_harness(Connectivity(nets=[_net("/A", "CLS"), gnd]), SPECS,
                         numberer=GroupPrefix(), known_numbers=legacy_store)
    got = {w.net: w.spec.wire_no for w in h.wires if w.b.ref != "J3"}
    assert got == {"/A": "M-007", "/GND": "M-008"}, got

    with tempfile.TemporaryDirectory() as td:
        store = WireNumberStore(os.path.join(td, WIRE_NUMBERS_NAME))
        store.save(legacy_store)
        store.save(collect_numbers(h), drop=legacy_keys(h))
        migrated = store.load()
        assert migrated["J1:1<->J2:1"] == "M-008"
        assert "/A" not in migrated and "/GND@J2:1" not in migrated
        assert migrated["/GONE"] == "M-009"


def test_store_roundtrip_merge_and_corrupt():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, WIRE_NUMBERS_NAME)
        store = WireNumberStore(path)
        assert store.load() == {}                    # missing file is fine
        store.save({"/A": "M-001", "/B": "M-002"})
        assert WireNumberStore(path).load() == {"/A": "M-001", "/B": "M-002"}

        # merge keeps entries for nets absent from this run (net comes back
        # later -> old number returns)
        store.save({"/C": "M-003"})
        data = json.load(open(path))
        assert data["numbers"] == {"/A": "M-001", "/B": "M-002", "/C": "M-003"}

        # corrupt file: load warns and returns {}, generation continues
        with open(path, "w") as fh:
            fh.write("{not json")
        broken = WireNumberStore(path)
        assert broken.load() == {}
        assert broken.warning, "expected a warning for corrupt store"


def test_plugin_writes_and_reuses_store():
    import tests.mock_pcbnew as mock
    from kicad_plugin.core import generate_harness_docs
    with tempfile.TemporaryDirectory() as td:
        board = mock.sample_board()
        r1 = generate_harness_docs(board, pcbnew_module=mock, out_dir=td,
                                   stem="p", emit_wireviz=False)
        store_path = os.path.join(td, WIRE_NUMBERS_NAME)
        assert store_path in r1.outputs and os.path.exists(store_path)
        csv1 = open(os.path.join(td, "p_wirelist.csv")).read()
        r2 = generate_harness_docs(board, pcbnew_module=mock, out_dir=td,
                                   stem="p", emit_wireviz=False)
        assert open(os.path.join(td, "p_wirelist.csv")).read() == csv1
        assert not [w for w in r2.warnings if "store" in w]


if __name__ == "__main__":
    test_numbers_survive_reordered_ingest()
    test_fresh_run_is_deterministic_without_store()
    test_new_net_gets_unused_number()
    test_explicit_and_intrinsic_numbers_beat_store()
    test_star_legs_have_stable_keys()
    test_legacy_net_name_keys_still_apply_and_migrate()
    test_store_roundtrip_merge_and_corrupt()
    test_plugin_writes_and_reuses_store()
    print("OK persistence: numbers stable across runs/reorderings; store "
          "round-trips, merges, and fails soft")
