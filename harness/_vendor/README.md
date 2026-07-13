# Vendored dependencies

- `yaml/` — PyYAML 6.0.1, pure-Python modules only (MIT, see `yaml/LICENSE`).
  Used as a fallback when the running Python (typically KiCad's bundled one)
  has no PyYAML installed; a system PyYAML always wins (`harness/yamlio.py`).
  The C-accelerated loader import fails cleanly and is not shipped.

- `wireviz_renderer.py` — small WireViz-compatible renderer for the subset emitted by this project. It lets the plugin render SVG/HTML/BOM outputs when the upstream `wireviz` command is not installed; Graphviz `dot` is optional and adds PNG output plus Graphviz-laid-out SVG.
