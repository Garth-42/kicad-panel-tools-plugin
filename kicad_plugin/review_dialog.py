"""Native wx editor for the generated wire-review CSV."""
from __future__ import annotations
import csv


def edit_review_csv(parent, path: str) -> bool:
    """Open a modal grid editor for *path*.

    Returns True when the user saves changes, so the caller can regenerate docs
    immediately from the edited review table.
    """
    import wx
    import wx.grid as gridlib

    rows, columns = _read_csv(path)
    dlg = wx.Dialog(parent, title="Wire Review Table")
    panel = wx.Panel(dlg)
    help_text = wx.StaticText(
        panel,
        label=("Edit wire_no and notes, then Save & Regenerate. "
               "Keep the key column unchanged."),
    )
    grid = gridlib.Grid(panel)
    grid.CreateGrid(max(len(rows), 1), len(columns))
    for col, name in enumerate(columns):
        grid.SetColLabelValue(col, name)
    for row_idx, row in enumerate(rows or [{}]):
        for col_idx, name in enumerate(columns):
            grid.SetCellValue(row_idx, col_idx, row.get(name, ""))
    for col_idx, name in enumerate(columns):
        if name == "key":
            attr = gridlib.GridCellAttr()
            attr.SetReadOnly(True)
            grid.SetColAttr(col_idx, attr)
        grid.AutoSizeColumn(col_idx, False)

    saved = {"value": False}

    def save_and_close(_evt):
        out_rows = []
        for row_idx in range(grid.GetNumberRows()):
            row = {}
            if not any(grid.GetCellValue(row_idx, c) for c in range(grid.GetNumberCols())):
                continue
            for col_idx, name in enumerate(columns):
                row[name] = grid.GetCellValue(row_idx, col_idx)
            out_rows.append(row)
        _write_csv(path, columns, out_rows)
        saved["value"] = True
        dlg.EndModal(wx.ID_SAVE)

    save = wx.Button(panel, wx.ID_SAVE, "Save && Regenerate")
    cancel = wx.Button(panel, wx.ID_CANCEL, "Cancel")
    save.Bind(wx.EVT_BUTTON, save_and_close)
    cancel.Bind(wx.EVT_BUTTON, lambda _evt: dlg.EndModal(wx.ID_CANCEL))

    buttons = wx.BoxSizer(wx.HORIZONTAL)
    buttons.AddStretchSpacer()
    buttons.Add(cancel, 0, wx.RIGHT, 8)
    buttons.Add(save, 0)

    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(help_text, 0, wx.EXPAND | wx.ALL, 10)
    sizer.Add(grid, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
    sizer.Add(buttons, 0, wx.EXPAND | wx.ALL, 10)
    panel.SetSizer(sizer)
    dlg.SetSize((1000, 600))
    dlg.ShowModal()
    dlg.Destroy()
    return saved["value"]


def _read_csv(path: str) -> tuple[list[dict], list[str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        columns = list(reader.fieldnames or [])
        rows = [{k: (v or "") for k, v in row.items() if k is not None}
                for row in reader]
    return rows, columns


def _write_csv(path: str, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
