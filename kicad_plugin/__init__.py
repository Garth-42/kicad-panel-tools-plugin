"""KiCad pcbnew Action Plugins for harness documentation.

Adds toolbar/menu actions in the PCB editor for generating harness documents and
for applying generated wire numbers back onto board net names.
"""
import os
import subprocess
import sys

# Make the sibling `harness` package importable regardless of where KiCad loaded
# us from (realpath resolves dev symlinks back to the repo).
_HERE = os.path.dirname(os.path.realpath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
for _PATH in (_HERE, _REPO_ROOT):
    if _PATH not in sys.path:
        sys.path.insert(0, _PATH)

try:
    import pcbnew
except ImportError:            # allows importing this module outside KiCad (tests)
    pcbnew = None

from harness.numbering import SCHEMES

from .core import apply_wire_names_to_board, generate_harness_docs
from . import panel_device_wizard  # noqa: F401  registers the footprint wizard
                                   # (it self-gates on pcbnew + FootprintWizardBase)

_Base = pcbnew.ActionPlugin if pcbnew is not None else object


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


def _toolbar_icon():
    return os.path.join(_HERE, "icon.xpm")


def _run_action(run, title):
    """Run/re-run one toolbar action, driven by the report dialog's buttons.

    A picked numbering scheme stays sticky for the rest of the loop (so a
    regenerate after a review-table edit doesn't fall back to the spec file's
    scheme), while `renumber` applies to a single run only.
    """
    scheme, renumber = None, False
    while True:
        res = run(scheme=scheme, renumber=renumber)
        renumber = False
        action = _report(res, title=title)
        if action == "regenerate":
            continue
        if isinstance(action, tuple) and action[0] == "renumber":
            scheme, renumber = action[1], True
            continue
        break


class HarnessDocsPlugin(_Base):
    def defaults(self):
        self.name = "Generate harness docs"
        self.category = "Documentation"
        self.description = "Export a wire list (+ WireViz) from the open board"
        icon = _toolbar_icon()
        self.show_toolbar_button = os.path.exists(icon)
        self.icon_file_name = icon

    def Run(self):
        board = pcbnew.GetBoard()
        _run_action(
            lambda **kw: generate_harness_docs(board, pcbnew_module=pcbnew, **kw),
            title="Harness docs")


class WireNamesPlugin(_Base):
    def defaults(self):
        self.name = "Apply wire numbers to net names"
        self.category = "Documentation"
        self.description = "Generate wire numbers and rename board nets to match"
        icon = _toolbar_icon()
        self.show_toolbar_button = os.path.exists(icon)
        self.icon_file_name = icon

    def Run(self):
        board = pcbnew.GetBoard()
        _run_action(
            lambda **kw: apply_wire_names_to_board(board, pcbnew_module=pcbnew, **kw),
            title="Wire names")


def _open_path(path):
    if not path:
        return
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _report(res, title="Harness docs"):
    lines = [f"{res.wire_count} wires exported.", "", "Wrote:"]
    lines += [f"  {p}" for p in res.outputs]
    if res.review_path:
        lines += ["", "Use Edit Review Table to change wire_no/notes in KiCad, or Open Review CSV for a spreadsheet.",
                  "To try a different numbering rule, pick a scheme below and Renumber."]
    if res.warnings:
        lines += ["", "Warnings:"] + [f"  {w}" for w in res.warnings]
    msg = "\n".join(lines)
    try:
        import wx
        from .review_dialog import edit_review_csv
        dlg = wx.Dialog(None, title=title)
        panel = wx.Panel(dlg)
        text = wx.TextCtrl(panel, value=msg, style=wx.TE_MULTILINE | wx.TE_READONLY)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        numbering = wx.BoxSizer(wx.HORIZONTAL)
        action = {"value": "close"}
        if res.review_path:
            scheme_choice = wx.Choice(panel, choices=list(SCHEMES))
            current = res.scheme if res.scheme in SCHEMES else "global"
            scheme_choice.SetStringSelection(current)
            renumber_btn = wx.Button(panel, label="Renumber from Scratch")
            renumber_btn.SetToolTip(
                "Discard persisted wire numbers (wire_numbers.json and the review "
                "table's wire_no column) and reassign every wire with the selected "
                "scheme")

            def renumber(_evt):
                chosen = scheme_choice.GetStringSelection() or current
                if wx.MessageBox(
                        "Discard ALL persisted wire numbers and reassign with "
                        f"scheme '{chosen}'?\n\nAlready-printed labels will no "
                        "longer match unless the design is re-exported everywhere.",
                        "Renumber from scratch",
                        wx.YES_NO | wx.ICON_WARNING, dlg) != wx.YES:
                    return
                action["value"] = ("renumber", chosen)
                dlg.EndModal(wx.ID_OK)

            renumber_btn.Bind(wx.EVT_BUTTON, renumber)
            numbering.Add(wx.StaticText(panel, label="Numbering scheme:"), 0,
                          wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
            numbering.Add(scheme_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
            numbering.Add(renumber_btn, 0, wx.ALIGN_CENTER_VERTICAL)
            edit_review = wx.Button(panel, label="Edit Review Table")
            open_review = wx.Button(panel, label="Open Review CSV")
            open_folder = wx.Button(panel, label="Open Folder")

            def edit_and_regenerate(_evt):
                if edit_review_csv(dlg, res.review_path):
                    action["value"] = "regenerate"
                    dlg.EndModal(wx.ID_OK)

            edit_review.Bind(wx.EVT_BUTTON, edit_and_regenerate)
            open_review.Bind(wx.EVT_BUTTON, lambda _evt: _open_path(res.review_path))
            open_folder.Bind(wx.EVT_BUTTON, lambda _evt: _open_path(os.path.dirname(res.review_path)))
            buttons.Add(edit_review, 0, wx.RIGHT, 8)
            buttons.Add(open_review, 0, wx.RIGHT, 8)
            buttons.Add(open_folder, 0, wx.RIGHT, 8)
        close = wx.Button(panel, wx.ID_OK, "Close")
        close.Bind(wx.EVT_BUTTON, lambda _evt: dlg.EndModal(wx.ID_OK))
        buttons.AddStretchSpacer()
        buttons.Add(close, 0)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(text, 1, wx.EXPAND | wx.ALL, 10)
        if res.review_path:
            sizer.Add(numbering, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        panel.SetSizer(sizer)
        dlg.SetSize((700, 420))
        dlg.ShowModal()
        dlg.Destroy()
        return action["value"]
    except Exception:
        print(msg)
    return "close"


def _register_action_plugin():
    """Register with pcbnew when KiCad imports the package.

    KiCad's plugin loader is the authority on when ActionPlugins should be
    registered. KiCad 10 asserts in C++ if ActionPlugin.register() runs before
    a GUI application handle exists, so headless imports leave registration to
    a later GUI import/refresh.
    """
    if pcbnew is None or not _have_wx_app():
        return
    for plugin_cls in (HarnessDocsPlugin, WireNamesPlugin):
        try:
            plugin_cls().register()
        except Exception as e:
            print(f"{plugin_cls.__name__} not registered: {e}", file=sys.stderr)


_register_action_plugin()
