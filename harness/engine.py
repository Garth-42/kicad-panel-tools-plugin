"""Assemble a Harness from Connectivity + specs. Pure logic, no I/O.

All value precedence lives here, in one ordered merge per net (_resolve_spec).
The rule: explicit YAML beats board-derived values, more specific YAML beats
less specific, and `defaults` is a last-resort fill. For each field the most
specific source that sets it wins:

    nets: (per-net override)                      highest
    cables.<id>.cores.<coreId>
    classes: (net class)  /  cables.<id> cable-level (fills what classes leave)
    board-derived (color swatch, track width -> gauge, routed length)
    defaults:                                     lowest

Extras (unknown keys -> CSV columns) merge the same way; the board contributes
none.
"""
from __future__ import annotations
from dataclasses import replace
from .model import Connectivity, Harness, Wire, WireSpec
from .specs import SpecStore
from .numbering import WireNumberer, GlobalSequence
from .cables import parse_cable_ref
from .persist import legacy_wire_key, wire_key


def _set_fields(spec: WireSpec, fields: dict, override: bool) -> None:
    for k, v in fields.items():
        if override or not getattr(spec, k):
            setattr(spec, k, str(v))


def _resolve_spec(net, specs: SpecStore) -> WireSpec:
    spec = WireSpec()

    # 1) net class(es) -- the explicit wire type
    cls_fields, cls_extra = specs.class_layer(getattr(net, "netclass", ""))
    _set_fields(spec, cls_fields, override=True)

    # 2) cable identity from the (group-bus) net name; declared cables only.
    #    A class can also assign a cable (without a conductor) by name.
    cable_id, conductor_id = parse_cable_ref(net.name, specs.cable_delimiter)
    if cable_id and cable_id in specs.cables:
        spec.cable = cable_id                       # physical cable id wins
        spec.conductor = conductor_id
    cable_extra: dict = {}
    core_extra: dict = {}
    if spec.cable:
        cable_fields, cable_extra = specs.cable_layer(spec.cable)
        _set_fields(spec, cable_fields, override=False)    # fills what classes left
        if spec.conductor:
            core_fields, core_extra = specs.core_layer(spec.cable, spec.conductor)
            _set_fields(spec, core_fields, override=True)  # per-core overrides

    # 3) per-net override -- highest precedence
    net_fields, net_extra = specs.net_layer(net.name)
    _set_fields(spec, net_fields, override=True)

    # 4) a cabled conductor gets an intrinsic label unless one was set explicitly
    if spec.cable and spec.conductor and not spec.wire_no:
        spec.wire_no = f"{spec.cable}-{spec.conductor}"

    # 5) board-derived values fill remaining gaps (never beat YAML):
    #      length <- summed routed track length (the cut length)
    #      color  <- net-class color swatch
    #      gauge  <- net-class track width, as a mm value
    #    Routed length spans the whole net, so it only names a cut length on a
    #    2-endpoint net (a >2 net expands into several wires; see build_harness).
    if (not spec.length_mm and getattr(net, "length_mm", None) is not None
            and len(net.nodes) == 2):
        spec.length_mm = f"{net.length_mm:.1f}"
    if not spec.color and getattr(net, "color", ""):
        spec.color = net.color
    if not spec.gauge and getattr(net, "track_width_mm", None) is not None:
        spec.gauge = f"{net.track_width_mm:.2f} mm"

    # 6) defaults are the last-resort fill
    d_fields, d_extra = specs.defaults_layer()
    _set_fields(spec, d_fields, override=False)

    # extras: ascending specificity, more specific keys overwrite
    extra: dict = {}
    for layer in (d_extra, cls_extra, cable_extra, core_extra, net_extra):
        extra.update(layer)
    spec.extra = extra
    return spec


def build_harness(conn: Connectivity, specs: SpecStore,
                  auto_number: bool = True,
                  numberer: WireNumberer | None = None,
                  known_numbers: dict | None = None) -> tuple[Harness, list[str]]:
    """Return (harness, warnings).

    Numbering: specs-supplied wire numbers always win; `known_numbers`
    ({wire_key: wire_no}, from a persisted store — see persist.py) re-applies
    previous runs' numbers next. For wires still without one, `numberer` fills
    them in (defaults to GlobalSequence), never reusing a number already taken.
    Assignment iterates wires in a sorted order so fresh numbers don't depend
    on the ingest source's net iteration order. Set auto_number=False to leave
    unnumbered wires blank.
    """
    warnings: list[str] = []
    wires: list[Wire] = []

    for net in conn.nets:
        spec = _resolve_spec(net, specs)

        nodes = net.nodes
        if len(nodes) < 2:
            warnings.append(f"net {net.name!r} has <2 endpoints; skipped")
            continue

        # 2 nodes -> one wire. >2 -> star from node[0] (v1 simplification);
        # nodes are sorted first so the hub (and each leg's persistence key)
        # doesn't depend on the ingest source's pad iteration order.
        if len(nodes) == 2:
            pairs = [(nodes[0], nodes[1])]
        else:
            nodes = sorted(nodes, key=lambda nd: (nd.ref, nd.pin))
            pairs = [(nodes[0], n) for n in nodes[1:]]
            msg = (f"net {net.name!r} has {len(nodes)} endpoints; "
                   f"expanded as a star from {nodes[0].ref}:{nodes[0].pin}")
            if getattr(net, "length_mm", None) is not None and not spec.length_mm:
                msg += (f"; routed length {net.length_mm:.1f} mm spans the whole"
                        f" net, per-leg length left blank")
            warnings.append(msg)

        for a, b in pairs:
            w = Wire(net=net.name, a=a, b=b, spec=replace(spec),
                     netclass=getattr(net, "netclass", ""))
            if known_numbers and not w.spec.wire_no:
                # endpoint key first; the v1 net-name key second, so stores and
                # review tables written before the key change keep working
                for key in (wire_key(a, b),
                            legacy_wire_key(net.name,
                                            b if len(pairs) > 1 else None)):
                    if known_numbers.get(key):
                        w.spec.wire_no = known_numbers[key]
                        break
            wires.append(w)

    if auto_number:
        order = sorted(wires, key=lambda w: (w.net, w.a.ref, w.a.pin,
                                             w.b.ref, w.b.pin))
        (numberer or GlobalSequence()).number(order)

    return Harness(wires=wires), warnings
