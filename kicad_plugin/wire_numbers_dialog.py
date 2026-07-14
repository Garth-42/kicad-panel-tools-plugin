"""Interactive wire-number editor: preview, tune, and apply in one session.

Nothing is written and no net is renamed until Apply & Finish — every Generate
round runs `preview_wire_numbers` (a dry run). The session logic (which cells
count as user overrides, what gets pinned at commit) lives in the pure helpers
below so it is testable without wx.
"""
from __future__ import annotations

from harness.numbering import SCHEMES
from harness.review import EDITABLE_COLUMNS, GENERATED_COLUMNS

from .core import apply_wire_names_to_board, preview_wire_numbers

READONLY_COLUMNS = set(GENERATED_COLUMNS) - EDITABLE_COLUMNS


def collect_overrides(baseline_rows, edited_rows, editable_columns) -> dict:
    """Diff the grid against the last computed table -> {key: {col: value}}.

    Only cells the user actually changed become overrides; a cleared cell
    yields an explicit "" (unpin — the store or the scheme fills it again)."""
    baseline = {r.get("key", ""): r for r in baseline_rows}
    out: dict = {}
    for row in edited_rows:
        key = row.get("key", "")
        base = baseline.get(key)
        if not key or base is None:
            continue
        for col in editable_columns:
            if col in row and row[col] != base.get(col, ""):
                out.setdefault(key, {})[col] = row[col]
    return out


def merge_overrides(accumulated: dict, new: dict) -> dict:
    """Fold one round's edits into the session's override map (in place)."""
    for key, cols in new.items():
        accumulated.setdefault(key, {}).update(cols)
    return accumulated


def commit_overrides(session_overrides: dict, final_rows) -> dict:
    """What Apply & Finish sends to the board: the user's accumulated edits,
    plus every displayed wire_no pinned so the committed board matches the
    approved table exactly. Other generated values (gauge from specs, color
    from the board, ...) are NOT pinned — freezing them into the review table
    would silently outlive later spec-file changes."""
    out = {k: dict(v) for k, v in session_overrides.items()}
    for row in final_rows:
        key = row.get("key", "")
        if key and str(row.get("wire_no", "")).strip():
            out.setdefault(key, {})["wire_no"] = row["wire_no"]
    return out


def run_wire_numbers_dialog(board, pcbnew_module, specs_path=None):
    """Modal editor; returns the applied Result, or None when cancelled."""
    import wx
    import wx.grid as gridlib

    res, columns, rows = preview_wire_numbers(board, pcbnew_module=pcbnew_module,
                                              specs_path=specs_path)
    editable = [c for c in columns
                if c in EDITABLE_COLUMNS or c not in GENERATED_COLUMNS]
    state = {"rows": rows, "overrides": {}, "renumbered": False, "result": None}

    dlg = wx.Dialog(None, title="Generate wire numbers",
                    style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    panel = wx.Panel(dlg)

    scheme_choice = wx.Choice(panel, choices=list(SCHEMES))
    scheme_choice.SetStringSelection(res.scheme if res.scheme in SCHEMES else "global")
    scheme_choice.SetToolTip("Pick a numbering scheme to renumber the table with "
                             "it right away. Numbers you typed stay pinned.")
    generate = wx.Button(panel, label="Generate")
    generate.SetToolTip("Re-roll every wire number with the selected scheme. "
                        "Numbers you typed into the table stay pinned; clear a "
                        "cell to unpin it.")
    help_text = wx.StaticText(
        panel,
        label=("Edit wire_no/notes directly, or pick a scheme to renumber the "
               "table with it (Generate re-rolls the current scheme). Nothing "
               "touches the board or any file until Apply && Finish."))

    grid = gridlib.Grid(panel)
    grid.CreateGrid(max(len(rows), 1), len(columns))
    for col_idx, name in enumerate(columns):
        grid.SetColLabelValue(col_idx, name)
        if name not in editable:
            attr = gridlib.GridCellAttr()
            attr.SetReadOnly(True)
            grid.SetColAttr(col_idx, attr)

    def refresh_grid(new_rows):
        grid.ClearGrid()
        want = max(len(new_rows), 1)
        have = grid.GetNumberRows()
        if want > have:
            grid.AppendRows(want - have)
        elif want < have:
            grid.DeleteRows(want, have - want)
        for row_idx, row in enumerate(new_rows or [{}]):
            for col_idx, name in enumerate(columns):
                grid.SetCellValue(row_idx, col_idx, str(row.get(name, "")))
        for col_idx in range(len(columns)):
            grid.AutoSizeColumn(col_idx, False)

    def read_grid():
        out = []
        for row_idx in range(grid.GetNumberRows()):
            row = {name: grid.GetCellValue(row_idx, col_idx)
                   for col_idx, name in enumerate(columns)}
            if any(row.values()):
                out.append(row)
        return out

    warnings_box = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
    warnings_box.SetMinSize((-1, 70))

    def show_warnings(result):
        warnings_box.SetValue("\n".join(result.warnings) if result.warnings
                              else "(no warnings)")

    refresh_grid(rows)
    show_warnings(res)

    def harvest_edits():
        merge_overrides(state["overrides"],
                        collect_overrides(state["rows"], read_grid(), editable))

    def on_generate(_evt):
        grid.SaveEditControlValue()
        harvest_edits()
        r, _cols, new_rows = preview_wire_numbers(
            board, pcbnew_module=pcbnew_module, specs_path=specs_path,
            scheme=scheme_choice.GetStringSelection(), renumber=True,
            overrides=state["overrides"])
        state["rows"] = new_rows
        state["renumbered"] = True
        refresh_grid(new_rows)
        show_warnings(r)

    def on_apply(_evt):
        grid.SaveEditControlValue()
        harvest_edits()
        final_rows = read_grid()
        state["result"] = apply_wire_names_to_board(
            board, pcbnew_module=pcbnew_module, specs_path=specs_path,
            scheme=scheme_choice.GetStringSelection(),
            renumber=state["renumbered"],
            overrides=commit_overrides(state["overrides"], final_rows))
        dlg.EndModal(wx.ID_OK)

    generate.Bind(wx.EVT_BUTTON, on_generate)
    # The scheme dropdown looks like it controls numbering, so make it: picking
    # a scheme renumbers immediately (same as Generate). Without this the choice
    # only takes effect on the next Generate click — so changing the scheme and
    # clicking Apply && Finish silently applies the *persisted* numbers (the
    # previously-generated scheme wins), which reads as "the prefix won't come
    # back". on_generate ignores its event arg, so it serves both.
    scheme_choice.Bind(wx.EVT_CHOICE, on_generate)
    apply_btn = wx.Button(panel, wx.ID_OK, "Apply && Finish")
    apply_btn.SetToolTip("Write wire_numbers.json + the review CSV and rename "
                         "the board nets to these numbers")
    cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
    apply_btn.Bind(wx.EVT_BUTTON, on_apply)
    cancel.Bind(wx.EVT_BUTTON, lambda _evt: dlg.EndModal(wx.ID_CANCEL))

    top = wx.BoxSizer(wx.HORIZONTAL)
    top.Add(wx.StaticText(panel, label="Numbering scheme:"), 0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
    top.Add(scheme_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
    top.Add(generate, 0, wx.ALIGN_CENTER_VERTICAL)

    buttons = wx.BoxSizer(wx.HORIZONTAL)
    buttons.AddStretchSpacer()
    buttons.Add(cancel, 0, wx.RIGHT, 8)
    buttons.Add(apply_btn, 0)

    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(top, 0, wx.EXPAND | wx.ALL, 10)
    sizer.Add(help_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
    sizer.Add(grid, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
    sizer.Add(warnings_box, 0, wx.EXPAND | wx.ALL, 10)
    sizer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
    panel.SetSizer(sizer)
    dlg.SetSize((1100, 650))
    dlg.ShowModal()
    dlg.Destroy()

    result = state["result"]
    if result is not None:
        summary = [f"{result.wire_count} wires numbered.", "", "Wrote:"]
        summary += [f"  {p}" for p in result.outputs]
        summary += ["", "Tip: enable Preferences > PCB Editor > Display Options >"
                        " Net Names to see the numbers on tracks and pads."]
        if result.warnings:
            summary += ["", "Warnings:"] + [f"  {w}" for w in result.warnings]
        wx.MessageBox("\n".join(summary), "Wire numbers applied",
                      wx.OK | wx.ICON_INFORMATION)
    return result
