import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.mock_pcbnew as mock
from kicad_plugin.core import generate_harness_docs

work = tempfile.mkdtemp()
# a net-class -> wire-type spec file sitting next to the "board"
specs = os.path.join(work, "harness_specs.yaml")
open(specs, "w").write(
    "classes:\n"
    "  \"14AWG_BN\": { cable: W1, gauge: \"14 AWG\", color: BN }\n"
    "  \"14AWG_BK\": { cable: W1, gauge: \"14 AWG\", color: BK }\n"
    "  \"18AWG_BU\": { cable: W2, gauge: \"18 AWG\", color: BU }\n")

res = generate_harness_docs(mock.sample_board(), pcbnew_module=mock,
                            specs_path=specs, out_dir=work, stem="demo")

print("wires:", res.wire_count)
print("outputs:", [os.path.basename(p) for p in res.outputs])
print("warnings:", res.warnings)
print("--- demo_wirelist.csv ---")
print(open(os.path.join(work, "demo_wirelist.csv")).read())

assert res.wire_count == 3
assert any(p.endswith("demo_wirelist.csv") for p in res.outputs)
csv = open(os.path.join(work, "demo_wirelist.csv")).read()
assert "320.0" in csv and "14 AWG" in csv and "-M1,U" in csv

# WireViz is part of the default output set (the toolbar button passes no
# flags): the YAML must always be emitted, and the rendered diagram must
# either be produced or be explained by a warning — never silently absent.
wv_yaml = os.path.join(work, "demo_harness.yaml")
assert wv_yaml in res.outputs and os.path.getsize(wv_yaml) > 0
if shutil.which("dot"):
    rendered = {os.path.splitext(p)[1] for p in res.outputs}
    assert {".png", ".svg", ".html"} <= rendered, res.outputs
else:
    assert any("Graphviz" in w for w in res.warnings), res.warnings

print("OK: plugin core produced wire list with net-class wire types + routed lengths")
print("OK: WireViz YAML emitted by default; render produced or explained")
shutil.rmtree(work)
