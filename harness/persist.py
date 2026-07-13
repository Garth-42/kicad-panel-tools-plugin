"""Wire-number persistence: keep numbers attached to the same physical wire
across re-exports (and across machines, where net iteration order differs).

The store is a JSON file (wire_numbers.json, next to the board/netlist):

    { "version": 1,
      "numbers": { "-M1:U<->X1:1": "M-001", "J1:1<->J3:1": "2", ... } }

Keys (stable-id contract, see docs/FREECAD_ROADMAP.md §7): a wire IS its two
endpoints, so the key is the sorted endpoint pair `ref:pin<->ref:pin`. Endpoint
keys survive net renames ("Apply wire numbers to net names") and schematic
re-syncs — net-name keys (the v1 contract, still read via `legacy_wire_key`)
went stale the moment that feature renamed the nets, which silently orphaned
review-table edits and churned numbers after a re-sync.

Numbers already present in the store are re-applied before the numbering
scheme runs (explicit spec numbers and intrinsic cable-core labels still win);
the schemes never reuse a number that any wire already carries, so persisted
and fresh numbers can't collide. Entries for wires that disappear are kept, so
a wire that comes back gets its old number again. Legacy net-name entries are
consulted as a fallback and dropped once the wire they describe has been
re-saved under its endpoint key.
"""
from __future__ import annotations
import json
import os

WIRE_NUMBERS_NAME = "wire_numbers.json"


def wire_key(a, b) -> str:
    """Stable identity for one wire: its two endpoint Nodes, order-independent.

    A pad belongs to exactly one net, so no two wires share an endpoint pair
    (star legs share the hub but never the far end)."""
    e = sorted([(str(a.ref), str(a.pin)), (str(b.ref), str(b.pin))])
    return f"{e[0][0]}:{e[0][1]}<->{e[1][0]}:{e[1][1]}"


def legacy_wire_key(net_name: str, leg_endpoint=None) -> str:
    """The v1 net-name key, kept read-only so old stores/review CSVs migrate.
    `leg_endpoint` is the far Node of a star-expanded leg; None for a net that
    yields a single wire."""
    if leg_endpoint is None:
        return net_name
    return f"{net_name}@{leg_endpoint.ref}:{leg_endpoint.pin}"


def _legacy_key_of(wire, net_wire_count: int) -> str:
    return legacy_wire_key(wire.net, wire.b if net_wire_count > 1 else None)


def _net_wire_counts(harness) -> dict:
    counts: dict = {}
    for w in harness.wires:
        counts[w.net] = counts.get(w.net, 0) + 1
    return counts


def collect_numbers(harness) -> dict:
    """harness -> {wire_key: wire_no} for every numbered wire."""
    return {wire_key(w.a, w.b): w.spec.wire_no
            for w in harness.wires if w.spec.wire_no}


def legacy_keys(harness) -> set:
    """The v1 keys of every wire in a harness — entries a save may purge,
    because those wires are being re-saved under endpoint keys."""
    counts = _net_wire_counts(harness)
    return {_legacy_key_of(w, counts[w.net]) for w in harness.wires}


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

    def save(self, numbers: dict, keep_existing: bool = True,
             drop: set | None = None) -> None:
        """Write the store; by default merge over what's already on disk so
        entries for temporarily-absent wires survive. `drop` removes keys made
        redundant by this save (legacy keys of wires now stored by endpoint)."""
        merged = dict(self.load()) if keep_existing else {}
        for key in (drop or ()):
            merged.pop(key, None)
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
