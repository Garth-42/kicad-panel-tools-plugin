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

This module only stores and slices the spec file into layers; the precedence
merge across layers (and board-derived values) lives in engine._resolve_spec.
"""
from __future__ import annotations

_FIELDS = ("cable", "wire_no", "gauge", "color", "length_mm", "prefix")


def split_fields(src: dict | None) -> tuple[dict, dict]:
    """Split one raw spec mapping into (known wire fields, extra passthrough).

    Known fields are stringified; empty strings are dropped so they never mask
    a lower layer. Unknown keys pass through untouched (they become CSV columns).
    """
    fields: dict = {}
    extra: dict = {}
    for k, v in (src or {}).items():
        if k in _FIELDS:
            if str(v) != "":
                fields[k] = str(v)
        else:
            extra[k] = v
    return fields, extra


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
        from .yamlio import import_yaml  # lazy; falls back to vendored copy
        yaml = import_yaml()
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return cls(defaults=data.get("defaults", {}),
                   nets=data.get("nets", {}),
                   classes=data.get("classes", {}),
                   cables=data.get("cables", {}),
                   numbering=data.get("numbering", ""),
                   cable_delimiter=data.get("cable_delimiter", "."))

    # ---- layers, consumed by engine._resolve_spec ---------------------------
    def class_layer(self, netclass: str) -> tuple[dict, dict]:
        """(fields, extra) merged from every matched net class.

        KiCad reports composite membership, e.g. "16AWG_MOTOR,Default"; split
        it, drop the implicit Default, and apply each named class in order.
        """
        fields: dict = {}
        extra: dict = {}
        for cname in (netclass or "").split(","):
            cname = cname.strip()
            if not cname or cname == "Default":
                continue
            f, e = split_fields(self.classes.get(cname))
            fields.update(f)
            extra.update(e)
        return fields, extra

    def cable_layer(self, cable: str) -> tuple[dict, dict]:
        """Cable-level facts for a declared cable (its cores: map excluded)."""
        cinfo = self.cables.get(cable) or {}
        return split_fields({k: v for k, v in cinfo.items() if k != "cores"})

    def core_layer(self, cable: str, conductor: str) -> tuple[dict, dict]:
        """Per-conductor detail for one core of a declared cable."""
        cores = (self.cables.get(cable) or {}).get("cores") or {}
        return split_fields(cores.get(conductor))

    def net_layer(self, net_name: str) -> tuple[dict, dict]:
        return split_fields(self.nets.get(net_name))

    def defaults_layer(self) -> tuple[dict, dict]:
        return split_fields(self.defaults)
