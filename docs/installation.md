# Installation

There are two independent front ends. Most people want the **plugin**; the CLI
is useful for CI, scripting, or schematics without footprints.

## The pcbnew plugin (board route)

Works on KiCad 9/10 (KiCad 7/8 supported with reduced net-class metadata).
No third-party Python packages are needed — a YAML reader is bundled.

### Option A — Plugin and Content Manager (recommended)

1. Grab the package zip — download the **harness-docs-pcm** artifact from the
   repo's CI (the downloaded `harness-docs-pcm.zip` is the installable
   package as-is), or build `dist/harness_docs_pcm.zip` yourself with
   `python3 scripts/build_pcm.py`.
2. In KiCad's project manager: **Plugin and Content Manager →
   Install from File…** and pick the zip. If PCM says *"Archive does not
   contain valid metadata.json file"*, the zip is a wrapper around the real
   package (e.g. an artifact downloaded from a CI run before this fix) —
   extract it once and install the zip found inside.
3. In the PCB editor: **Tools → External Plugins → Refresh** (or restart).
   **Generate harness docs** appears in that menu, and the **Panel device**
   wizard appears in the Footprint Editor's wizard list.

### Option B — manual copy

1. Open your board in the PCB editor and choose
   **Tools → External Plugins → Open Plugin Directory**. KiCad opens the exact
   folder it scans — paths differ per OS and version, so let KiCad tell you.
2. Copy **both** folders from this repository into that directory, side by
   side:
   - `kicad_plugin/`
   - `harness/`

   (The plugin imports `harness` as a sibling — it won't load without it.)
3. Back in the PCB editor: **Tools → External Plugins → Refresh**.

Developer alternative: keep the repo wherever you like and symlink just
`kicad_plugin/` into the plugin directory — the plugin resolves the repo root
through the symlink, so `harness/` stays importable.

## The CLI (netlist route)

Needs Python ≥ 3.10; nothing to install (PyYAML is used if present, with a
bundled fallback otherwise).

Export a netlist from your schematic and run the tool from the repo root:

```
kicad-cli sch export netlist --format kicadxml -o design.net.xml design.kicad_sch
python -m harness design.net.xml --specs harness_specs.yaml --csv design_wirelist.csv
```

With KiCad 9/10's `kicad-cli`, the netlist carries your net-class assignments,
so wire types work on this route too. Lengths don't — only the routed board
knows those.

## Rendering diagrams

The plugin now bundles a WireViz-compatible renderer for the YAML it emits, so
**Generate harness docs** can write `*_harness.svg`, `.html`, and `.bom.tsv`
without installing the upstream WireViz Python package or Graphviz. If Graphviz
`dot` is available, the plugin also writes `*_harness.png` and uses Graphviz for
the SVG layout.

```
# Optional: install the full upstream WireViz CLI; the plugin uses it when found.
pip install wireviz
wireviz design_harness.yaml  # -> .png, .svg, .html, .bom.tsv
```
