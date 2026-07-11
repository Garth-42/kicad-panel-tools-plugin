import sys, tempfile, os; sys.path.insert(0, ".")
from harness.model import Connectivity, Net, Node
from harness.specs import SpecStore
from harness.engine import build_harness
conn = Connectivity(components={}, nets=[
    Net("1","/W5.L1",[Node("X1","1"),Node("M1","U")]),
    Net("2","/W5.L2",[Node("X1","2"),Node("M1","V")]),
    Net("3","/W5.PE",[Node("X1","3"),Node("M1","PE")]),
    Net("6","3.3V",[Node("X1","6"),Node("U1","VCC")]),
])
specs = SpecStore(cables={"W5":{"gauge":"1.5 mm2","shield":"yes","conductor_count":3,
    "cores":{"L1":{"color":"BN"},"L2":{"color":"BK"},"PE":{"color":"GNYE"}}}})
h,_ = build_harness(conn, specs)
byc={(w.spec.cable,w.spec.conductor):w for w in h.wires}
assert byc[("W5","L1")].spec.color=="BN" and byc[("W5","L1")].spec.wire_no=="W5-L1"
assert byc[("W5","PE")].spec.color=="GNYE"
assert byc[("W5","L1")].spec.extra.get("shield")=="yes"
assert byc[("W5","L1")].spec.extra.get("conductor_count")==3   # int count -> column
assert next(w for w in h.wires if w.net=="3.3V").spec.cable==""
print("OK: cores map + integer count column both work; decoy ignored")
