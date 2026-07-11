"""Assemble a Harness from Connectivity + specs. Pure logic, no I/O."""
from __future__ import annotations
from dataclasses import replace
from .model import Connectivity, Harness, Wire
from .specs import SpecStore
from .numbering import WireNumberer, GlobalSequence
from .cables import parse_cable_ref
from .specs import _FIELDS


def build_harness(conn: Connectivity, specs: SpecStore,
                  auto_number: bool = True,
                  numberer: WireNumberer | None = None) -> tuple[Harness, list[str]]:
    """Return (harness, warnings).

    Numbering: specs-supplied wire numbers always win. For wires without one,
    `numberer` fills them in (defaults to GlobalSequence). Set auto_number=False
    to leave them blank.
    """
    warnings: list[str] = []
    wires: list[Wire] = []

    for net in conn.nets:
        spec = specs.resolve(net.name, getattr(net, "netclass", ""))
        # Board-sourced fallbacks (YAML wins if it set these explicitly):
        #   length  <- summed routed track length (the cut length)
        #   color   <- net-class color swatch
        #   gauge   <- net-class track width, as a mm value
        if not spec.length_mm and getattr(net, "length_mm", None) is not None:
            spec.length_mm = f"{net.length_mm:.1f}"
        if not spec.color and getattr(net, "color", ""):
            spec.color = net.color
        if not spec.gauge and getattr(net, "track_width_mm", None) is not None:
            spec.gauge = f"{net.track_width_mm:.2f} mm"

        # --- multi-conductor cable identity, from the (group-bus) net name ---
        cable_id, conductor_id = parse_cable_ref(net.name, specs.cable_delimiter)
        if cable_id and cable_id in specs.cables:      # declared cable only
            spec.cable = cable_id                      # physical cable id wins
            spec.conductor = conductor_id

        # Merge the cable registry: cable-level facts fill empties + extras;
        # the per-conductor map (keyed by core id) is the most specific and wins.
        cinfo = specs.cables.get(spec.cable, {}) if spec.cable else {}
        for k, v in cinfo.items():
            if k == "cores":
                continue
            if k in _FIELDS:
                if not getattr(spec, k):
                    setattr(spec, k, str(v))
            else:
                spec.extra.setdefault(k, v)
        if spec.conductor:
            core = (cinfo.get("cores", {}) or {}).get(spec.conductor, {})
            for k, v in (core or {}).items():
                if k in _FIELDS:
                    setattr(spec, k, str(v))           # per-core overrides
                else:
                    spec.extra.setdefault(k, v)
            # Cabled core gets an intrinsic label: cable + core (e.g. W5-L1).
            if not spec.wire_no:
                spec.wire_no = f"{spec.cable}-{spec.conductor}"
        nodes = net.nodes
        if len(nodes) < 2:
            warnings.append(f"net {net.name!r} has <2 endpoints; skipped")
            continue

        # 2 nodes -> one wire. >2 -> star from node[0] (v1 simplification).
        pairs = ([(nodes[0], nodes[1])] if len(nodes) == 2
                 else [(nodes[0], n) for n in nodes[1:]])
        if len(nodes) > 2:
            warnings.append(
                f"net {net.name!r} has {len(nodes)} endpoints; "
                f"expanded as a star from {nodes[0].ref}:{nodes[0].pin}")

        for a, b in pairs:
            wires.append(Wire(net=net.name, a=a, b=b, spec=replace(spec),
                              netclass=getattr(net, "netclass", "")))

    if auto_number:
        (numberer or GlobalSequence()).number(wires)

    return Harness(wires=wires), warnings
