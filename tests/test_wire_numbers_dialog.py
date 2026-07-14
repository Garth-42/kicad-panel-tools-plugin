"""Interactive wire-numbers session: the wx-free logic behind the dialog.

Covers the dialog's contract end to end without a GUI: preview is a pure dry
run, user edits become overrides that pin numbers through Generate rounds, and
Apply & Finish commits exactly the approved table to the board.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kicad_plugin.core import (apply_wire_names_to_board,  # noqa: E402
                               generate_harness_docs, preview_wire_numbers)
from kicad_plugin.wire_numbers_dialog import (collect_overrides,  # noqa: E402
                                              commit_overrides, merge_overrides)
from harness.review import EDITABLE_COLUMNS  # noqa: E402
from tests import mock_pcbnew as mock  # noqa: E402

W1_U = "-M1:U<->X1:1"


def test_preview_is_a_pure_dry_run():
    with tempfile.TemporaryDirectory() as td:
        res, columns, rows = preview_wire_numbers(
            mock.sample_board(), pcbnew_module=mock, out_dir=td, stem="p")
        assert res.wire_count == 3 and res.scheme == "global"
        assert {r["key"] for r in rows} == {W1_U, "-M1:V<->X1:2", "-KM1:A1<->X1:3"}
        assert all(r["wire_no"] for r in rows)
        assert os.listdir(td) == [], "preview must not write any file"


def test_overrides_pin_numbers_through_generate_rounds():
    with tempfile.TemporaryDirectory() as td:
        board = mock.sample_board()
        _res, _cols, rows = preview_wire_numbers(board, pcbnew_module=mock,
                                                 out_dir=td, stem="p")
        # the user types a number into one cell of the displayed table
        edited = [dict(r, wire_no="MOTOR-7") if r["key"] == W1_U else dict(r)
                  for r in rows]
        overrides = merge_overrides({}, collect_overrides(rows, edited,
                                                          EDITABLE_COLUMNS))
        assert overrides == {W1_U: {"wire_no": "MOTOR-7"}}

        # Generate with a different scheme: the pinned cell survives, the rest
        # renumber; still nothing on disk
        res2, _cols, rows2 = preview_wire_numbers(
            board, pcbnew_module=mock, out_dir=td, stem="p",
            scheme="srcdst", renumber=True, overrides=overrides)
        by_key = {r["key"]: r["wire_no"] for r in rows2}
        assert by_key[W1_U] == "MOTOR-7"
        assert by_key["-KM1:A1<->X1:3"] == "X1:3--KM1:A1"
        assert os.listdir(td) == []


def test_commit_applies_exactly_the_approved_table():
    with tempfile.TemporaryDirectory() as td:
        board = mock.sample_board()
        _res, _cols, rows = preview_wire_numbers(board, pcbnew_module=mock,
                                                 out_dir=td, stem="p")
        session = {W1_U: {"wire_no": "MOTOR-7", "notes": "field check"}}
        final = [dict(r, **session.get(r["key"], {})) for r in rows]
        overrides = commit_overrides(session, final)
        # every displayed number is pinned; user edits carried verbatim
        assert all("wire_no" in v for v in overrides.values())
        assert overrides[W1_U]["notes"] == "field check"

        res = apply_wire_names_to_board(board, pcbnew_module=mock, out_dir=td,
                                        stem="p", overrides=overrides)
        pad_nets = {pad.GetNetname() for fp in board.GetFootprints()
                    for pad in fp.Pads()}
        assert "/MOTOR-7" in pad_nets
        assert res.wire_count == 3
        # the note landed in the written review table
        with open(os.path.join(td, "p_wire_review.csv"), encoding="utf-8") as fh:
            assert "field check" in fh.read()


def test_scheme_change_renumbers_over_persisted_numbers():
    # The dialog binds the scheme dropdown to a renumber-preview, so picking a
    # new scheme takes effect over numbers persisted under an earlier scheme —
    # what you see is what Apply writes. (Before, only the Generate button
    # renumbered; changing the scheme and clicking Apply re-applied the OLD
    # persisted numbers, which read as "the new scheme's prefix won't come back".)
    with tempfile.TemporaryDirectory() as td:
        board = mock.sample_board()
        # a prior run persists global numbers (bare digits) to wire_numbers.json
        generate_harness_docs(board, pcbnew_module=mock, out_dir=td, stem="p",
                              emit_wireviz=False)
        # dialog opens: the persisted global numbers are shown untouched
        _res, _cols, opened = preview_wire_numbers(board, pcbnew_module=mock,
                                                   out_dir=td, stem="p")
        assert all(r["wire_no"].isdigit() for r in opened), opened

        # picking 'srcdst' regenerates immediately (the dropdown -> renumber),
        # so the table now shows endpoint-derived numbers, not the persisted ones
        _res, _cols, picked = preview_wire_numbers(
            board, pcbnew_module=mock, out_dir=td, stem="p",
            scheme="srcdst", renumber=True, overrides={})
        assert all(":" in r["wire_no"] for r in picked), picked

        # Apply & Finish commits exactly that table onto the board net names
        apply_wire_names_to_board(
            board, pcbnew_module=mock, out_dir=td, stem="p",
            scheme="srcdst", renumber=True, overrides=commit_overrides({}, picked))
        pad_nets = {pad.GetNetname() for fp in board.GetFootprints()
                    for pad in fp.Pads()}
        # the persisted global names are gone; the srcdst names are on the board
        assert not any(n.lstrip("/").isdigit() for n in pad_nets), pad_nets
        assert any(":" in n for n in pad_nets), pad_nets


if __name__ == "__main__":
    test_preview_is_a_pure_dry_run()
    test_overrides_pin_numbers_through_generate_rounds()
    test_commit_applies_exactly_the_approved_table()
    test_scheme_change_renumbers_over_persisted_numbers()
    print("OK wire numbers dialog: preview is dry, edits pin through renumber, "
          "commit applies the approved table to the board, and a scheme change "
          "renumbers over persisted numbers")
