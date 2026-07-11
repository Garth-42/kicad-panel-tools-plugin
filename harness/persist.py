"""Wire-number persistence: keep numbers attached to the same physical wire
across re-exports (and across machines, where net iteration order differs).

The store is a JSON file (wire_numbers.json, next to the board/netlist):

    { "version": 1,
      "numbers": { "/START": "M-001", "/GND@J3:1": "2", ... } }

Keys (stable-id contract, see docs/FREECAD_ROADMAP.md §7):
  * a plain 2-endpoint net -> the net name (endpoint order never matters);
  * a star-expanded leg    -> "<net>@<ref>:<pin>" of the leg's far endpoint
    (the engine sorts a >2-endpoint net's nodes, so the hub is deterministic).

Numbers already present in the store are re-applied before the numbering
scheme runs (explicit spec numbers and intrinsic cable-core labels still win);
the schemes never reuse a number that any wire already carries, so persisted
and fresh numbers can't collide. Entries for nets that disappear are kept, so
a net that comes back gets its old number again.
"""
from __future__ import annotations
import json
import os

WIRE_NUMBERS_NAME = "wire_numbers.json"


def wire_key(net_name: str, leg_endpoint=None) -> str:
    """Stable identity for one wire. `leg_endpoint` is the far Node of a
    star-expanded leg; None for a net that yields a single wire."""
    if leg_endpoint is None:
        return net_name
    return f"{net_name}@{leg_endpoint.ref}:{leg_endpoint.pin}"


def collect_numbers(harness) -> dict:
    """harness -> {wire_key: wire_no} for every numbered wire."""
    per_net: dict = {}
    for w in harness.wires:
        per_net.setdefault(w.net, []).append(w)
    out: dict = {}
    for net_name, wires in per_net.items():
        for w in wires:
            if not w.spec.wire_no:
                continue
            key = wire_key(net_name, w.b if len(wires) > 1 else None)
            out[key] = w.spec.wire_no
    return out


class WireNumberStore:
    """Load/save the wire-number JSON. Never raises on a missing or corrupt
    file — persistence must not break doc generation; check `.warning`."""

    def __init__(self, path: str):
        self.path = path
        self.warning = ""

    def load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
            numbers = data.get("numbers", {})
            if not isinstance(numbers, dict):
                raise ValueError("'numbers' is not a mapping")
            return {str(k): str(v) for k, v in numbers.items()}
        except Exception as e:
            self.warning = (f"wire-number store '{os.path.basename(self.path)}'"
                            f" not loaded: {e}")
            return {}

    def save(self, numbers: dict, keep_existing: bool = True) -> None:
        """Write the store; by default merge over what's already on disk so
        entries for temporarily-absent nets survive."""
        merged = dict(self.load()) if keep_existing else {}
        merged.update(numbers)
        payload = {"version": 1,
                   "numbers": {k: merged[k] for k in sorted(merged)}}
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=1, sort_keys=False)
                fh.write("\n")
        except Exception as e:
            self.warning = (f"wire-number store '{os.path.basename(self.path)}'"
                            f" not saved: {e}")
