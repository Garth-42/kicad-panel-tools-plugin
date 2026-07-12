import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.yamlio import import_yaml
yaml = import_yaml()
import tests.mock_pcbnew as mock
from harness.ingest import KicadBoardSource
from harness.specs import SpecStore
from harness.engine import build_harness
from harness.numbering import GlobalSequence, PerCable, Equipotential, SourceDestination
from harness.emit.wireviz_yaml import build_wireviz

conn = KicadBoardSource.from_board(mock.sample_board(), pcbnew_module=mock).load()
specs = SpecStore(classes={
    "14AWG_BN": {"cable": "W1", "gauge": "14 AWG", "color": "BN"},
    "14AWG_BK": {"cable": "W1", "gauge": "14 AWG", "color": "BK"},
    "18AWG_BU": {"cable": "W2", "gauge": "18 AWG", "color": "BU"},
})

def numbers(numberer):
    h, _ = build_harness(conn, specs, numberer=numberer)
    return [(w.net, w.spec.wire_no) for w in h.wires]

print("global:", numbers(GlobalSequence(width=3)))
print("cable :", numbers(PerCable()))
print("net   :", numbers(Equipotential(prefix="N", width=2)))
print("srcdst:", numbers(SourceDestination()))

# --- numbering assertions ---
g = dict(numbers(GlobalSequence()));      assert set(g.values()) == {"1","2","3"}
c = dict(numbers(PerCable()));            assert "W1-001" in c.values() and "W2-001" in c.values()
n = dict(numbers(Equipotential()));       assert len(set(n.values())) == 3   # one per net
sd = dict(numbers(SourceDestination()));  assert sd["/W1_U"] == "X1:1--M1:U"  # -M1 designator has its own leading dash
print("OK numbering: all four schemes behave as specified")

# --- WireViz refinement checks ---
h, _ = build_harness(conn, specs, numberer=PerCable())
wv = build_wireviz(h, components=conn.components)

# connector type from component value (not the designator); BOM field surfaced
assert wv["connectors"]["-M1"]["type"] == "Motor_3ph"
assert wv["connectors"]["-M1"]["mpn"] == "ABB-M3"          # from footprint field
# real pin ids preserved; numeric pins are ints (matches WireViz's coercion of
# connection refs — see emit/wireviz_yaml._pin_id), alpha pins stay strings
assert wv["connectors"]["X1"]["pins"] == [1, 2, 3]
assert wv["connectors"]["-M1"]["pins"] == ["U", "V"]

W1 = wv["cables"]["W1"]
assert W1["wirecount"] == 2
assert len(W1["colors"]) == W1["wirecount"]                 # colors match wirecount
assert len(W1["wirelabels"]) == W1["wirecount"]            # labels match wirecount
# W2 has a single routed length -> should carry length + unit
W2 = wv["cables"]["W2"]
assert W2.get("length") == 450.0 and W2.get("length_unit") == "mm"
# connection sets well-formed: [ {conn:[pin]}, {cable:[i]}, {conn:[pin]} ]
for cs in wv["connections"]:
    assert len(cs) == 3 and all(isinstance(x, dict) for x in cs)

# round-trips as YAML
with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
    yaml.safe_dump(wv, fh, sort_keys=False)
    path = fh.name
yaml.safe_load(open(path))
print("OK WireViz: types/BOM/pins correct, colors&labels match wirecount, cable length set, valid YAML")
print("\n--- W1 cable block ---")
print(yaml.safe_dump({"W1": W1}, sort_keys=False))
