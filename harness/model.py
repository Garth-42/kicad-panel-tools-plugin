"""Pure data model. No I/O, no KiCad-specific logic lives here."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Node:
    """One pin of one component that a net touches."""
    ref: str            # component designator, e.g. "J1", "-M1"
    pin: str            # pin number/name, e.g. "1", "U"
    pinfunction: str = ""  # human pin name if the symbol provides one


@dataclass
class Component:
    ref: str
    value: str = ""
    fields: dict = field(default_factory=dict)  # custom symbol fields


@dataclass
class Net:
    code: str
    name: str
    nodes: list[Node] = field(default_factory=list)
    netclass: str = ""              # net class name (-> wire type, if you encode it there)
    length_mm: float | None = None  # summed routed track length; only the board adapter fills this
    color: str = ""                 # net-class color from the board (hex), if set
    track_width_mm: float | None = None  # net-class track width from the board


@dataclass
class Connectivity:
    """Everything an ingest source must provide, KiCad-agnostic."""
    components: dict = field(default_factory=dict)  # ref -> Component
    nets: list = field(default_factory=list)        # list[Net]


@dataclass
class WireSpec:
    """Resolved harness metadata for a net."""
    cable: str = ""
    wire_no: str = ""
    gauge: str = ""
    color: str = ""
    length_mm: str = ""
    prefix: str = ""   # wire-number group key (e.g. "M" for motor wires)
    conductor: str = ""  # core id within a multi-conductor cable (from W5.L1 -> "L1")
    extra: dict = field(default_factory=dict)  # arbitrary passthrough (conductors, shield, ...)


@dataclass
class Wire:
    """A point-to-point conductor derived from a net."""
    net: str
    a: Node
    b: Node
    spec: WireSpec
    netclass: str = ""


@dataclass
class Harness:
    wires: list = field(default_factory=list)  # list[Wire]

    def cables(self) -> dict:
        """Group wires by cable name -> list[Wire]."""
        out: dict = {}
        for w in self.wires:
            out.setdefault(w.spec.cable or "(loose)", []).append(w)
        return out
