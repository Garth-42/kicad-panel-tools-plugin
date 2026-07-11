"""KiCad pcbnew Action Plugin: 'Generate harness docs'.

Reads the currently open board, extracts connectivity + routed cut-lengths, and
writes a wire list (and WireViz YAML) next to the board file. Appears under
Tools -> External Plugins in the PCB editor.

Install: copy or symlink this `kicad_plugin` folder into your KiCad plugin path
(Tools -> External Plugins -> Open Plugin Directory shows it), then
Tools -> External Plugins -> Refresh. See README for per-OS paths.
"""
import os
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

from .core import generate_harness_docs

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


def _report(res):
    lines = [f"{res.wire_count} wires exported.", "", "Wrote:"]
    lines += [f"  {p}" for p in res.outputs]
    if res.warnings:
        lines += ["", "Warnings:"] + [f"  {w}" for w in res.warnings]
    msg = "\n".join(lines)
    try:
        import wx
        wx.MessageBox(msg, "Harness docs")
    except Exception:
        print(msg)


def _in_kicad_gui() -> bool:
    """True only when a KiCad wxApp is running. Prevents ActionPlugin.register()
    from asserting during headless `python -m kicad_plugin ...` runs."""
    try:
        import wx
        return wx.GetApp() is not None
    except Exception:
        return False


if pcbnew is not None and _in_kicad_gui():
    HarnessDocsPlugin().register()
