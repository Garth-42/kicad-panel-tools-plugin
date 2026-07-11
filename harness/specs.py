"""Per-net harness metadata, joined to KiCad connectivity by net name.

Because KiCad wires are nets (no place to store gauge/color/length), the harness
build data lives here, in a spec file keyed by net name, with optional defaults.
Symbol custom fields (read via the netlist) can also feed specs later; for now the
spec file is the single source of truth for wire-level attributes.

Spec file (YAML) shape:

    defaults:
      gauge: "20 AWG"
      color: ""
    nets:
      "/SIG1":
        cable: W1
        wire_no: "101"
        gauge: "18 AWG"
        color: RD
        length_mm: "250"
"""
from __future__ import annotations
from .model import WireSpec

_FIELDS = ("cable", "wire_no", "gauge", "color", "length_mm", "prefix")


class SpecStore:
    def __init__(self, defaults: dict | None = None, nets: dict | None = None,
                 classes: dict | None = None, cables: dict | None = None,
                 numbering: str = "", cable_delimiter: str = "."):
        self.defaults = defaults or {}
        self.nets = nets or {}
        self.classes = classes or {}   # netclass name -> {gauge/color/cable/...}
        self.cables = cables or {}     # cable name -> {shield/jacket/conductors:{...}}
        self.numbering = numbering     # optional scheme name, e.g. "group"
        self.cable_delimiter = cable_delimiter or "."

    @classmethod
    def from_file(cls, path: str) -> "SpecStore":
        import yaml  # lazy: KiCad's bundled Python may lack PyYAML
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return cls(defaults=data.get("defaults", {}),
                   nets=data.get("nets", {}),
                   classes=data.get("classes", {}),
                   cables=data.get("cables", {}),
                   numbering=data.get("numbering", ""),
                   cable_delimiter=data.get("cable_delimiter", "."))

    def resolve(self, net_name: str, netclass: str = "") -> WireSpec:
        # Precedence: defaults < net class(es) < per-net override.
        merged = {k: str(self.defaults.get(k, "")) for k in _FIELDS}
        # KiCad reports composite membership, e.g. "16AWG_MOTOR,Default".
        # Split it, drop the implicit Default, and apply each matching class.
        class_sources = [self.classes.get(c.strip(), {})
                         for c in netclass.split(",")
                         if c.strip() and c.strip() != "Default"]
        extra: dict = {}
        for src in (*class_sources, self.nets.get(net_name, {})):
            for k, v in (src or {}).items():
                if k in _FIELDS and str(v) != "":
                    merged[k] = str(v)
                elif k not in _FIELDS:            # arbitrary passthrough field
                    extra[k] = v
        return WireSpec(extra=extra, **merged)
