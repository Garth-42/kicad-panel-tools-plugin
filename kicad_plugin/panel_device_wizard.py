"""'Panel device' footprint wizard: 2D device representations in one minute.

Panel gear (contactors, breakers, PSUs, terminal strips) rarely has KiCad
footprints, which makes the harness-as-board workflow feel like a blank page.
Nearly all of it is: a rectangle W x H with one or two rows of terminals at
some pitch. This wizard generates exactly that — body outline on F.Fab (+ a
silkscreen box), named terminal pads top/bottom — from a handful of numbers.

It appears in the PCB editor's footprint editor under
New Footprint Using Wizard -> "Panel device". Terminal labels are free text
("L1,L2,L3,A1"), so contactor/breaker naming just works. Untick "draw outline"
to overlay artwork imported from a datasheet image instead (Image Converter).

`build_panel_device()` is the UI-independent core; scripts/gen_panel_library.py
uses it to generate the starter library, and tests drive it headless.
"""
from __future__ import annotations

try:
    import pcbnew as _pcbnew
except ImportError:            # importable outside KiCad (tests, docs tooling)
    _pcbnew = None

try:
    import FootprintWizardBase  # provided by KiCad's scripting/plugins path
    _Base = FootprintWizardBase.FootprintWizard
except Exception:
    FootprintWizardBase = None
    _Base = object


def _have_wx_app():
    try:
        import wx
    except Exception:
        return False
    app_cls = getattr(wx, "App", None)
    get_instance = getattr(app_cls, "GetInstance", None) if app_cls is not None else None
    try:
        if callable(get_instance):
            return get_instance() is not None
        get_app = getattr(wx, "GetApp", None)
        return callable(get_app) and get_app() is not None
    except Exception:
        return False


def _split_labels(text, count, start=1):
    """'L1,L2,L3' -> labels; empty text -> ['<start>', ...] numeric run."""
    labels = [t.strip() for t in (text or "").split(",") if t.strip()]
    if labels:
        return labels
    return [str(start + i) for i in range(max(count, 0))]


def build_panel_device(pcb, fp, *, width_mm, height_mm,
                       top_labels=(), bottom_labels=(),
                       top_pitch_mm=10.0, bottom_pitch_mm=10.0,
                       pad_mm=4.0, inset_mm=5.0, draw_outline=True,
                       outline_width_mm=0.15):
    """Populate FOOTPRINT `fp` with a panel-device body + terminal pads.

    Coordinates are footprint-local, body centered on the origin; the top
    terminal row sits `inset_mm` below the top edge, the bottom row above the
    bottom edge. Rows are centered horizontally at their pitch. Pads are
    circular SMD on F.Cu (wiring attach points — nothing is soldered).
    """
    mm = pcb.FromMM
    V = pcb.VECTOR2I
    w, h = mm(width_mm), mm(height_mm)

    if draw_outline:
        for layer, grow in ((pcb.F_Fab, 0.0), (pcb.F_SilkS, 0.3)):
            g = mm(grow)
            s = pcb.PCB_SHAPE(fp)
            s.SetShape(pcb.SHAPE_T_RECTANGLE)
            s.SetStart(V(-w // 2 - g, -h // 2 - g))
            s.SetEnd(V(w // 2 + g, h // 2 + g))
            s.SetLayer(layer)
            s.SetWidth(mm(outline_width_mm))
            fp.Add(s)

    def add_row(labels, pitch_mm, y):
        n = len(labels)
        if n == 0:
            return
        pitch = mm(pitch_mm)
        x0 = -pitch * (n - 1) // 2
        for i, label in enumerate(labels):
            pad = pcb.PAD(fp)
            pad.SetShape(pcb.PAD_SHAPE_CIRCLE)
            pad.SetAttribute(pcb.PAD_ATTRIB_SMD)
            pad.SetSize(V(mm(pad_mm), mm(pad_mm)))
            ls = pcb.LSET()
            ls.AddLayer(pcb.F_Cu)
            ls.AddLayer(pcb.F_Mask)
            pad.SetLayerSet(ls)
            pad.SetNumber(str(label))
            pad.SetPosition(V(x0 + i * pitch, y))
            fp.Add(pad)

    add_row(list(top_labels), top_pitch_mm, -h // 2 + mm(inset_mm))
    add_row(list(bottom_labels), bottom_pitch_mm, h // 2 - mm(inset_mm))

    # reference above the body, value below (fab-style)
    fp.Reference().SetPosition(V(0, -h // 2 - mm(3)))
    fp.Value().SetPosition(V(0, h // 2 + mm(3)))
    return fp


class PanelDeviceWizard(_Base):
    def GetName(self):
        return "Panel device"

    def GetDescription(self):
        return ("Rectangular panel device (contactor, breaker, PSU, terminal "
                "strip) with named terminal rows — for 1:1 panel wiring layouts")

    def GetValue(self):
        return self.parameters["Body"]["name"]

    def GenerateParameterList(self):
        self.AddParam("Body", "name", self.uString, "DIN_Device")
        self.AddParam("Body", "width", self.uMM, 45.0, min_value=2)
        self.AddParam("Body", "height", self.uMM, 90.0, min_value=2)
        self.AddParam("Body", "draw outline", self.uBool, True)
        self.AddParam("Terminals", "top count", self.uInteger, 3, min_value=0)
        self.AddParam("Terminals", "top labels", self.uString, "")
        self.AddParam("Terminals", "top pitch", self.uMM, 10.0, min_value=1)
        self.AddParam("Terminals", "bottom count", self.uInteger, 3, min_value=0)
        self.AddParam("Terminals", "bottom labels", self.uString, "")
        self.AddParam("Terminals", "bottom pitch", self.uMM, 10.0, min_value=1)
        self.AddParam("Terminals", "pad diameter", self.uMM, 4.0, min_value=0.5)
        self.AddParam("Terminals", "edge inset", self.uMM, 5.0, min_value=0)

    def CheckParameters(self):
        pass

    def BuildThisFootprint(self):
        body = self.parameters["Body"]
        term = self.parameters["Terminals"]
        top = _split_labels(term["top labels"], term["top count"], start=1)
        bottom = _split_labels(term["bottom labels"], term["bottom count"],
                               start=len(top) + 1)
        build_panel_device(
            _pcbnew, self.module,
            width_mm=pcbnew_to_mm(body["width"]),
            height_mm=pcbnew_to_mm(body["height"]),
            top_labels=top, bottom_labels=bottom,
            top_pitch_mm=pcbnew_to_mm(term["top pitch"]),
            bottom_pitch_mm=pcbnew_to_mm(term["bottom pitch"]),
            pad_mm=pcbnew_to_mm(term["pad diameter"]),
            inset_mm=pcbnew_to_mm(term["edge inset"]),
            draw_outline=bool(body["draw outline"]),
        )


def pcbnew_to_mm(value):
    """Wizard uMM params arrive in internal units (nm); builder wants mm."""
    return _pcbnew.ToMM(int(value)) if _pcbnew is not None else float(value)


if _pcbnew is not None and FootprintWizardBase is not None and _have_wx_app():
    PanelDeviceWizard().register()
