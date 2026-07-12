"""KiCad pcbnew Action Plugin: 'Generate harness docs'.

Reads the currently open board, extracts connectivity + routed cut-lengths, and
writes a wire list (and WireViz YAML) next to the board file. Appears under
Tools -> External Plugins in the PCB editor.

Install: copy or symlink this `kicad_plugin` folder into your KiCad plugin path
(Tools -> External Plugins -> Open Plugin Directory shows it), then
Tools -> External Plugins -> Refresh. See README for per-OS paths.
"""
import os
import subprocess
import sys

# Make the sibling `harness` package importable regardless of where KiCad loaded
# us from (realpath resolves dev symlinks back to the repo).
_HERE = os.path.dirname(os.path.realpath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import pcbnew
except ImportError:            # allows importing this module outside KiCad (tests)
    pcbnew = None

from .core import apply_wire_names_to_board, generate_harness_docs
from . import panel_device_wizard  # noqa: F401  registers the footprint wizard
                                   # (it self-gates on pcbnew + FootprintWizardBase)

_Base = pcbnew.ActionPlugin if pcbnew is not None else object


class HarnessDocsPlugin(_Base):
    def defaults(self):
        self.name = "Generate harness docs"
        self.category = "Documentation"
        self.description = "Export a wire list (+ WireViz) from the open board"
        icon = os.path.join(_HERE, "icon.png")
        # Only claim a toolbar button if we actually ship an icon; the menu entry
        # under Tools -> External Plugins always appears regardless.
        self.show_toolbar_button = os.path.exists(icon)
        self.icon_file_name = icon

    def Run(self):
        board = pcbnew.GetBoard()
        res = generate_harness_docs(board, pcbnew_module=pcbnew)
        _report(res)



class WireNamesPlugin(_Base):
    def defaults(self):
        self.name = "Apply wire numbers to net names"
        self.category = "Documentation"
        self.description = "Generate wire numbers and rename board nets to match"
        icon = os.path.join(_HERE, "icon.xpm")
        self.show_toolbar_button = os.path.exists(icon)
        self.icon_file_name = icon

    def Run(self):
        board = pcbnew.GetBoard()
        res = apply_wire_names_to_board(board, pcbnew_module=pcbnew)
        _report_title(res, "Wire names")

def _open_path(path):
    if not path:
        return
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _report_title(res, title="Harness docs"):
    return _report(res, title=title)

def _report(res, title="Harness docs"):
    lines = [f"{res.wire_count} wires exported.", "", "Wrote:"]
    lines += [f"  {p}" for p in res.outputs]
    if res.review_path:
        lines += ["", "Edit the wire review CSV, save it, then run this command again to apply changes."]
    if res.warnings:
        lines += ["", "Warnings:"] + [f"  {w}" for w in res.warnings]
    msg = "\n".join(lines)
    try:
        import wx
        dlg = wx.Dialog(None, title=title)
        panel = wx.Panel(dlg)
        text = wx.TextCtrl(panel, value=msg, style=wx.TE_MULTILINE | wx.TE_READONLY)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        if res.review_path:
            open_review = wx.Button(panel, label="Open Review CSV")
            open_folder = wx.Button(panel, label="Open Folder")
            open_review.Bind(wx.EVT_BUTTON, lambda _evt: _open_path(res.review_path))
            open_folder.Bind(wx.EVT_BUTTON, lambda _evt: _open_path(os.path.dirname(res.review_path)))
            buttons.Add(open_review, 0, wx.RIGHT, 8)
            buttons.Add(open_folder, 0, wx.RIGHT, 8)
        close = wx.Button(panel, wx.ID_OK, "Close")
        close.Bind(wx.EVT_BUTTON, lambda _evt: dlg.EndModal(wx.ID_OK))
        buttons.AddStretchSpacer()
        buttons.Add(close, 0)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(text, 1, wx.EXPAND | wx.ALL, 10)
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        panel.SetSizer(sizer)
        dlg.SetSize((700, 420))
        dlg.ShowModal()
        dlg.Destroy()
    except Exception:
        print(msg)


def _report_with_native_editor(res, title="Harness docs"):
    lines = [f"{res.wire_count} wires exported.", "", "Wrote:"]
    lines += [f"  {p}" for p in res.outputs]
    if res.review_path:
        lines += ["", "Use Edit Review Table to change wire_no/notes in KiCad, or Open Review CSV for a spreadsheet."]
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
        action = {"value": "close"}
        if res.review_path:
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
        sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        panel.SetSizer(sizer)
        dlg.SetSize((700, 420))
        dlg.ShowModal()
        dlg.Destroy()
        return action["value"]
    except Exception:
        print(msg)
    return "close"


def _run_with_native_editor(self):
    board = pcbnew.GetBoard()
    while True:
        res = generate_harness_docs(board, pcbnew_module=pcbnew)
        if _report_with_native_editor(res) != "regenerate":
            break


def _defaults_with_toolbar(self):
    self.name = "Generate harness docs"
    self.category = "Documentation"
    self.description = "Export a wire list (+ WireViz) from the open board"
    icon = os.path.join(_HERE, "icon.xpm")
    self.show_toolbar_button = os.path.exists(icon)
    self.icon_file_name = icon


HarnessDocsPlugin.Run = _run_with_native_editor
HarnessDocsPlugin.defaults = _defaults_with_toolbar

def _register_action_plugin():
    """Register with pcbnew when KiCad imports the package.

    KiCad's plugin loader is the authority on when ActionPlugins should be
    registered.  Do not require a wx.App here: some KiCad/PCM load paths import
    Python plugins before wx.GetApp() is visible to Python, which silently hid
    the Tools -> External Plugins menu item.  Headless runs that can import
    pcbnew (for example ``python -m kicad_plugin``) may still reject
    ActionPlugin.register(), so registration failures are reported but do not
    make the command-line wrapper unusable.
    """
    if pcbnew is None:
        return
    try:
        HarnessDocsPlugin().register()
        WireNamesPlugin().register()
    except Exception as e:
        print(f"Harness docs KiCad action plugin not registered: {e}", file=sys.stderr)


_register_action_plugin()
