import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.mock_pcbnew as mock
from harness.ingest.pcbnew_board import KicadBoardSource

conn = KicadBoardSource.from_board(mock.sample_board(), pcbnew_module=mock).load()

print("components:", sorted(conn.components))
print("-M1 fields:", conn.components["-M1"].fields)
for n in conn.nets:
    ep = ", ".join(f"{nd.ref}:{nd.pin}" for nd in n.nodes)
    L = f"{n.length_mm} mm" if n.length_mm is not None else "-"
    print(f"  net {n.name:10} class={n.netclass or '-':9} len={L:9} [{ep}]")

# assertions on the mapping
byname = {n.name: n for n in conn.nets}
assert byname["/W1_U"].length_mm == 320.0, byname["/W1_U"].length_mm   # 300+20, via excluded
assert byname["/CTRL_A1"].length_mm == 450.0
assert byname["/W1_U"].netclass == "14AWG_BN"
assert {nd.ref for nd in byname["/W1_U"].nodes} == {"X1", "-M1"}
assert conn.components["-M1"].fields.get("MPN") == "ABB-M3"
print("\nOK: footprints/pads/tracks/nets/lengths mapped correctly")
