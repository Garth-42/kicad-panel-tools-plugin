import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.mock_pcbnew as mock
from harness.ingest import KicadBoardSource
from harness.specs import SpecStore
from harness.engine import build_harness
from harness.emit import write_csv

conn = KicadBoardSource.from_board(mock.sample_board(), pcbnew_module=mock).load()

# adapter picked up net-class color + width for the CTRL_A1 net
ctrl = next(n for n in conn.nets if n.name == "/CTRL_A1")
print("CTRL_A1: color=", ctrl.color, " width_mm=", ctrl.track_width_mm)
assert ctrl.color == "#FF0000"
assert ctrl.track_width_mm == 1.5

# specs: NO color/gauge for the motor class -> should fall back to the board values.
# cables: section declares number of conductors -> becomes an 'extra' column.
specs = SpecStore(
    classes={
        "18AWG_BU": {"cable": "WM"},           # deliberately no gauge/color here
        "14AWG_BN": {"cable": "W1", "gauge": "14 AWG", "color": "BN"},
        "14AWG_BK": {"cable": "W1", "gauge": "14 AWG", "color": "BK"},
    },
    cables={
        "WM": {"conductors": 3, "shield": "yes"},
        "W1": {"conductors": 2},
    })

harness, _ = build_harness(conn, specs)
out = os.path.join(tempfile.mkdtemp(), "wl.csv")
write_csv(harness, out)
print("\n" + open(out).read())

wm = next(w for w in harness.wires if w.spec.cable == "WM")
assert wm.spec.color == "#FF0000", wm.spec.color        # color from board swatch
assert wm.spec.gauge == "1.50 mm", wm.spec.gauge        # diameter from board track width
assert wm.spec.extra.get("conductors") == 3             # cable-level conductor count
assert wm.spec.extra.get("shield") == "yes"
header = open(out).readline()
assert "conductors" in header and "shield" in header    # extra columns present
print("OK: conductors passthrough + board color + board diameter all flow to the CSV")
