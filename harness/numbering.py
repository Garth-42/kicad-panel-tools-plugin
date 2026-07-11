"""Wire-numbering strategies.

Each strategy fills `Wire.spec.wire_no` for wires that don't already have a number
(numbers coming from specs are always respected). Pick one and pass it to
build_harness(); the engine stays agnostic to which scheme you use.

Schemes:
  GlobalSequence   1, 2, 3, ...                      (simple running count)
  PerCable         W1-001, W1-002, W2-001, ...        (cable-scoped, harness-style)
  Equipotential    one number per net, shared by all  (IEC-style: a conductor
                   segments of that net                 number belongs to a potential)
  SourceDestination  X1:1-M1:U  (derived from ends)    (terminal/from-to naming)
"""
from __future__ import annotations
from abc import ABC, abstractmethod


class WireNumberer(ABC):
    @abstractmethod
    def number(self, wires) -> None:
        """Assign spec.wire_no in place for wires whose number is empty."""


def _fmt(n: int, width: int) -> str:
    return f"{n:0{width}d}" if width else str(n)


class GlobalSequence(WireNumberer):
    def __init__(self, start: int = 1, prefix: str = "", width: int = 0):
        self.start, self.prefix, self.width = start, prefix, width

    def number(self, wires) -> None:
        n = self.start
        for w in wires:
            if w.spec.wire_no:
                continue
            w.spec.wire_no = f"{self.prefix}{_fmt(n, self.width)}"
            n += 1


class PerCable(WireNumberer):
    """Cable-scoped running count, e.g. W1-001. Loose wires get a bare count."""
    def __init__(self, sep: str = "-", width: int = 3, start: int = 1):
        self.sep, self.width, self.start = sep, width, start

    def number(self, wires) -> None:
        counters: dict[str, int] = {}
        for w in wires:
            if w.spec.wire_no:
                continue
            cable = w.spec.cable or ""
            n = counters.get(cable, self.start)
            counters[cable] = n + 1
            num = _fmt(n, self.width)
            w.spec.wire_no = f"{cable}{self.sep}{num}" if cable else num


class Equipotential(WireNumberer):
    """IEC-style: every conductor on the same net carries one shared number.

    When a net expands into several segments (e.g. a star from one point), all of
    them get the same wire number, because they are the same electrical potential.
    """
    def __init__(self, start: int = 1, prefix: str = "", width: int = 0):
        self.start, self.prefix, self.width = start, prefix, width

    def number(self, wires) -> None:
        assigned: dict[str, str] = {}
        n = self.start
        for w in wires:
            if w.spec.wire_no:
                continue
            if w.net not in assigned:
                assigned[w.net] = f"{self.prefix}{_fmt(n, self.width)}"
                n += 1
            w.spec.wire_no = assigned[w.net]


class SourceDestination(WireNumberer):
    """Wire id derived from its two endpoints (terminal-based naming)."""
    def __init__(self, fmt: str = "{fr}:{fp}-{tr}:{tp}"):
        self.fmt = fmt

    def number(self, wires) -> None:
        for w in wires:
            if w.spec.wire_no:
                continue
            w.spec.wire_no = self.fmt.format(
                fr=w.a.ref, fp=w.a.pin, tr=w.b.ref, tp=w.b.pin)


class GroupPrefix(WireNumberer):
    """Unique names grouped by a category prefix: M-001, M-002, C-001, ...

    Group key per wire = spec.prefix if set, else spec.cable. Every wire sharing a
    group gets a running count within that group, so all motor wires (prefix "M")
    number M-001, M-002... regardless of which nets/classes they came from. Wires
    with neither a prefix nor a cable get a bare running number.
    """
    def __init__(self, sep: str = "-", width: int = 3, start: int = 1):
        self.sep, self.width, self.start = sep, width, start

    def number(self, wires) -> None:
        counters: dict[str, int] = {}
        for w in wires:
            if w.spec.wire_no:
                continue
            group = (getattr(w.spec, "prefix", "") or w.spec.cable or "").strip()
            n = counters.get(group, self.start)
            counters[group] = n + 1
            num = _fmt(n, self.width)
            w.spec.wire_no = f"{group}{self.sep}{num}" if group else num


# name -> factory, for the CLI
SCHEMES = {
    "global": GlobalSequence,
    "cable": PerCable,
    "net": Equipotential,
    "srcdst": SourceDestination,
    "group": GroupPrefix,
}
