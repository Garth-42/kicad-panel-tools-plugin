"""Minimal stand-in for the pcbnew API surface the adapter touches.
Lets us prove the footprint/pad/track/net/length mapping without real KiCad."""

class _Color:
    def __init__(self, r, g, b, a=1.0): self.r, self.g, self.b, self.a = r, g, b, a
    def ToCSSString(self): return "#%02X%02X%02X" % (int(self.r*255), int(self.g*255), int(self.b*255))

class _NetClass:
    def __init__(self, name, width_nm=0, color=None):
        self._n, self._w, self._col = name, width_nm, color
    def GetName(self): return self._n
    def GetTrackWidth(self): return self._w
    def GetPcbColor(self): return self._col

class _Net:
    def __init__(self, name, netclass="", width_nm=0, color=None):
        self._n, self._c = name, netclass
        self._nc = _NetClass(netclass, width_nm, color)
    def GetNetClassName(self): return self._c
    def GetNetClass(self): return self._nc

class _Pad:
    def __init__(self, number, netname, netclass="", width_nm=0, color=None):
        self._num, self._net = number, _Net(netname, netclass, width_nm, color)
    def GetNumber(self): return self._num
    def GetNetname(self): return self._net._n
    def GetNet(self): return self._net

class _Footprint:
    def __init__(self, ref, value, fields, pads):
        self._ref, self._val, self._fields, self._pads = ref, value, fields, pads
    def GetReference(self): return self._ref
    def GetValue(self): return self._val
    def GetFieldsText(self): return dict(self._fields)
    def Pads(self): return self._pads

class _Track:
    def __init__(self, netname, length_nm, is_via=False):
        self._net, self._len, self._via = netname, length_nm, is_via
    def GetClass(self): return "PCB_VIA" if self._via else "PCB_TRACK"
    def GetNetname(self): return self._net
    def GetLength(self): return self._len

class _Board:
    def __init__(self, footprints, tracks, filename=""):
        self._fp, self._tk, self._fn = footprints, tracks, filename
    def GetFileName(self): return self._fn
    def GetFootprints(self): return self._fp
    def GetTracks(self): return self._tk

# module-level helper the adapter uses
def ToMM(nm): return nm / 1_000_000.0

def sample_board():
    MM = 1_000_000  # nm per mm
    fps = [
        _Footprint("X1", "Terminal_3", {}, [
            _Pad("1", "/W1_U", "14AWG_BN"),
            _Pad("2", "/W1_V", "14AWG_BK"),
            _Pad("3", "/CTRL_A1", "18AWG_BU", width_nm=int(1.5*1_000_000), color=_Color(1.0,0.0,0.0)),
        ]),
        _Footprint("-M1", "Motor_3ph", {"MPN": "ABB-M3"}, [
            _Pad("U", "/W1_U"), _Pad("V", "/W1_V"),
        ]),
        _Footprint("-KM1", "Contactor", {}, [_Pad("A1", "/CTRL_A1")]),
    ]
    tracks = [
        _Track("/W1_U", 300*MM), _Track("/W1_U", 20*MM),   # 320 mm total
        _Track("/W1_V", 305*MM),
        _Track("/CTRL_A1", 450*MM),
        _Track("/CTRL_A1", 0, is_via=True),                # via ignored
    ]
    return _Board(fps, tracks, filename="/tmp/htest/demo.kicad_pcb")
