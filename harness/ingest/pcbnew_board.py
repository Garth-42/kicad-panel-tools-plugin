"""Ingest connectivity + routed lengths from a KiCad PCB ('harness-as-board').

This is the deepest-integration route: pcbnew is the one KiCad editor with a real
plugin API, it's a hand-placed view linked to the schematic netlist, and — uniquely
— its routed tracks have a measurable length, which becomes the wire cut length that
nothing else in the pipeline could supply.

Harness-concept mapping:

    board footprint   -> Component     (ref, value, custom fields)
    footprint pad     -> Node          (ref, pad number) attached to a net
    board net         -> Net           (code, name, netclass)
    tracks on a net   -> Net.length_mm (summed routed length, the cut length)

Two ways to obtain the board object, both supported by `from_board`/`from_path`:
  * inside a pcbnew Action/IPC plugin:  KicadBoardSource.from_board(pcbnew.GetBoard())
  * standalone / headless script:       KicadBoardSource.from_path("design.kicad_pcb")

NOTE ON API STABILITY: pcbnew's SWIG method names drift across KiCad versions, and
this module is written defensively (each accessor tries a couple of known spellings).
The SWIG `pcbnew` module currently exposes the fullest board access, including track
lengths; the IPC API (kicad-python) is the supported future path, so once its PCB
coverage includes geometry you can reimplement `_length_mm`/iteration against it
without touching anything above this file. Verify method names against your build.
"""
from __future__ import annotations
from .base import ConnectivitySource
from ..model import Connectivity, Component, Net, Node


def _first(obj, *method_names, default=None):
    """Call the first method that exists on obj; tolerate API renames."""
    for name in method_names:
        fn = getattr(obj, name, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                continue
    return default


class KicadBoardSource(ConnectivitySource):
    def __init__(self, board, pcbnew_module=None):
        """`board` is a pcbnew BOARD; `pcbnew_module` is the imported `pcbnew`
        (kept injectable so the mapping can be unit-tested without real KiCad)."""
        self.board = board
        self.pcb = pcbnew_module

    # ---- constructors -------------------------------------------------------
    @classmethod
    def from_board(cls, board, pcbnew_module=None):
        if pcbnew_module is None:
            import pcbnew  # only needed when running inside/against KiCad
            pcbnew_module = pcbnew
        return cls(board, pcbnew_module)

    @classmethod
    def from_path(cls, path: str):
        import pcbnew
        return cls(pcbnew.LoadBoard(path), pcbnew)

    # ---- helpers ------------------------------------------------------------
    def _to_mm(self, internal_units) -> float:
        """pcbnew stores geometry in nanometers; convert to mm."""
        if self.pcb is not None and hasattr(self.pcb, "ToMM"):
            return float(self.pcb.ToMM(internal_units))
        return float(internal_units) / 1_000_000.0  # nm -> mm fallback

    # ---- ConnectivitySource -------------------------------------------------
    def load(self) -> Connectivity:
        conn = Connectivity()

        # 1) footprints -> Components; pads -> nodes grouped by net name
        nodes_by_net: dict[str, list[Node]] = {}
        netclass_by_net: dict[str, str] = {}
        color_by_net: dict[str, str] = {}
        width_by_net: dict[str, float | None] = {}

        for fp in _first(self.board, "GetFootprints", "Footprints", default=[]) or []:
            ref = _first(fp, "GetReference", default="") or ""
            value = _first(fp, "GetValue", default="") or ""
            fields = self._footprint_fields(fp)
            conn.components[ref] = Component(ref=ref, value=value, fields=fields)

            for pad in _first(fp, "Pads", "GetPads", default=[]) or []:
                pin = _first(pad, "GetNumber", "GetName", default="") or ""
                netname = _first(pad, "GetNetname", default="") or ""
                if not netname:
                    continue  # unconnected pad
                nodes_by_net.setdefault(netname, []).append(
                    Node(ref=ref, pin=str(pin)))
                if netname not in netclass_by_net:
                    netclass_by_net[netname] = self._pad_netclass(pad)
                    nc = self._netclass_obj(pad)
                    color_by_net[netname] = self._netclass_color(nc)
                    width_by_net[netname] = self._netclass_width_mm(nc)

        # 2) tracks -> summed routed length per net (the cut length)
        length_by_net: dict[str, float] = {}
        for trk in _first(self.board, "GetTracks", "Tracks", default=[]) or []:
            # skip vias/arcs-as-vias; count copper track segments only
            cls = _first(trk, "GetClass", default="")
            if cls and "VIA" in str(cls).upper():
                continue
            netname = _first(trk, "GetNetname", default="") or ""
            if not netname:
                continue
            seg_len = _first(trk, "GetLength", default=0) or 0
            length_by_net[netname] = length_by_net.get(netname, 0.0) + self._to_mm(seg_len)

        # 3) assemble Nets
        code = 0
        for netname, nodes in nodes_by_net.items():
            code += 1
            conn.nets.append(Net(
                code=str(code),
                name=netname,
                nodes=nodes,
                netclass=netclass_by_net.get(netname, ""),
                length_mm=round(length_by_net[netname], 3) if netname in length_by_net else None,
                color=color_by_net.get(netname, ""),
                track_width_mm=width_by_net.get(netname),
            ))
        return conn

    # ---- version-tolerant field/netclass access ------------------------------
    def _footprint_fields(self, fp) -> dict:
        # KiCad 7+: GetFieldsText() -> {name: text}. Older: GetProperties().
        d = _first(fp, "GetFieldsText", "GetProperties", default=None)
        if isinstance(d, dict):
            return dict(d)
        fields = {}
        for f in _first(fp, "GetFields", default=[]) or []:
            name = _first(f, "GetName", default="")
            text = _first(f, "GetText", "GetShownText", default="")
            if name:
                fields[str(name)] = str(text)
        return fields

    def _pad_netclass(self, pad) -> str:
        net = _first(pad, "GetNet", default=None)
        if net is None:
            return ""
        # KiCad 7+: net.GetNetClassName(); some builds: net.GetNetClass().GetName()
        name = _first(net, "GetNetClassName", default="") or ""
        if name:
            return name
        nc = _first(net, "GetNetClass", default=None)
        if nc is not None:
            return _first(nc, "GetName", default="") or ""
        return ""

    def _netclass_obj(self, pad):
        net = _first(pad, "GetNet", default=None)
        return _first(net, "GetNetClass", default=None) if net is not None else None

    def _netclass_width_mm(self, nc):
        if nc is None:
            return None
        w = _first(nc, "GetTrackWidth", default=None)
        if not w:                      # 0 or None -> unset
            return None
        return round(self._to_mm(w), 3)

    def _netclass_color(self, nc):
        """Net-class color swatch -> #RRGGBB. Empty if unset (alpha 0)."""
        if nc is None:
            return ""
        col = _first(nc, "GetPcbColor", "GetSchematicColor", default=None)
        if col is None:
            return ""
        try:
            if float(getattr(col, "a", 1)) == 0.0:   # transparent = "no color set"
                return ""
        except Exception:
            pass
        css = _first(col, "ToCSSString", "ToHexString", default="")
        if isinstance(css, str) and css.startswith("#"):
            return css[:7].upper()
        try:
            return "#%02X%02X%02X" % (int(col.r * 255), int(col.g * 255), int(col.b * 255))
        except Exception:
            return ""
