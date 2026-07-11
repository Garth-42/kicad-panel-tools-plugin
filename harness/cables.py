"""Parse multi-conductor cable membership from a net name.

KiCad named group buses produce member net names like "W5.L1" (bus name "W5",
member "L1"), optionally under a hierarchical sheet path ("/Sheet/W5.L1").
We read the cable id and conductor id from that structure.

A dotted net is only treated as a cable core when its prefix is a *declared*
cable (a key in the spec's `cables:` section). That keeps power nets such as
"3.3V" or "+1.8V" from being misread as cable "3" / "+1".
"""
from __future__ import annotations


def parse_cable_ref(net_name: str, delimiter: str = ".") -> tuple[str | None, str | None]:
    base = (net_name or "").rsplit("/", 1)[-1]      # drop hierarchical sheet path
    if delimiter and delimiter in base:
        cable, _, conductor = base.partition(delimiter)
        if cable and conductor:
            return cable, conductor
    return None, None
