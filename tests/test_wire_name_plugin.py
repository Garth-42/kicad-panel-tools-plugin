import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kicad_plugin.core import apply_wire_names_to_board  # noqa: E402
from tests import mock_pcbnew as mock  # noqa: E402


def _pad_numbers(board):
    return [str(pad.GetNumber()) for fp in board.GetFootprints() for pad in fp.Pads()]


def test_wire_names_are_applied_to_board_nets():
    with tempfile.TemporaryDirectory() as td:
        board = mock.sample_board()
        res = apply_wire_names_to_board(board, pcbnew_module=mock, out_dir=td, stem="p")
        pad_nets = [pad.GetNetname() for fp in board.GetFootprints() for pad in fp.Pads()]
        track_nets = [track.GetNetname() for track in board.GetTracks() if "VIA" not in track.GetClass()]
        assert res.wire_count == 3
        assert "/1" in pad_nets
        assert "/2" in pad_nets
        assert "/3" in pad_nets
        assert set(track_nets) == {"/1", "/2", "/3"}
        assert any(o.endswith("p_wire_review.csv") for o in res.outputs)
        assert any("3 board net name" in o for o in res.outputs)


def test_reapplying_wire_names_never_touches_pads_and_is_stable():
    """Regression: a reapply whose freshly computed numbers differ from the
    (already renamed) net names — on real boards this happens by itself,
    because netclass prefixes are pattern-matched against the OLD net names —
    once fell through to PAD.SetName (the pad NUMBER, a legacy pcbnew alias of
    SetNumber), since GetNetsByName stays keyed by the original names after a
    rename. Real KiCad then silently DROPPED pads whose new number collided
    numerically with a sibling's ("002" vs "2"), and every rerun churned all
    wire numbers (P-001 -> 001 -> ...). A renamed net must keep its number and
    pads must never be touched."""
    with tempfile.TemporaryDirectory() as td:
        board = mock.sample_board()
        pads_before = _pad_numbers(board)

        apply_wire_names_to_board(board, pcbnew_module=mock, out_dir=td, stem="p")
        first_nets = sorted(pad.GetNetname() for fp in board.GetFootprints()
                            for pad in fp.Pads())
        assert _pad_numbers(board) == pads_before, "first run renamed a pad"

        # Anything that would number the wires differently on the second run —
        # here a scheme change, on a real board the lost netclass prefixes.
        specs = os.path.join(td, "specs.yaml")
        with open(specs, "w", encoding="utf-8") as fh:
            fh.write("numbering: srcdst\n")

        res2 = apply_wire_names_to_board(board, pcbnew_module=mock, out_dir=td,
                                         stem="p", specs_path=specs)
        second_nets = sorted(pad.GetNetname() for fp in board.GetFootprints()
                             for pad in fp.Pads())
        assert _pad_numbers(board) == pads_before, "second run renamed a pad"
        assert second_nets == first_nets, "reapply must keep the same numbers"
        assert res2.wire_count == 3


def test_review_edit_after_apply_renames_the_net():
    """Regression: review keys used to be NET NAMES, so the first apply —
    which renames the nets — orphaned every row; a wire_no typed into the
    review table after that was silently dropped ('key no longer exists').
    Endpoint keys survive the rename, so the edit must now reach the board."""
    with tempfile.TemporaryDirectory() as td:
        board = mock.sample_board()
        apply_wire_names_to_board(board, pcbnew_module=mock, out_dir=td, stem="p")

        review = os.path.join(td, "p_wire_review.csv")
        import csv
        with open(review, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            if row["key"] == "-M1:U<->X1:1":
                row["wire_no"] = "MOTOR-7"
        with open(review, "w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=rows[0].keys())
            wr.writeheader(); wr.writerows(rows)

        res = apply_wire_names_to_board(board, pcbnew_module=mock, out_dir=td,
                                        stem="p")
        pad_nets = {pad.GetNetname() for fp in board.GetFootprints()
                    for pad in fp.Pads()}
        assert "/MOTOR-7" in pad_nets, (pad_nets, res.warnings)
        assert not [w for w in res.warnings if "no longer exists" in w], res.warnings


def test_renumber_reapplies_fresh_names_to_already_renamed_nets():
    """The explicit escape hatch from the stability above: renumber=True must
    treat nets already named their numbers as fresh, reassign with the picked
    scheme, and rename the board nets again — still without touching pads."""
    with tempfile.TemporaryDirectory() as td:
        board = mock.sample_board()
        pads_before = _pad_numbers(board)
        apply_wire_names_to_board(board, pcbnew_module=mock, out_dir=td, stem="p")

        res = apply_wire_names_to_board(board, pcbnew_module=mock, out_dir=td,
                                        stem="p", scheme="srcdst", renumber=True)
        pad_nets = {pad.GetNetname() for fp in board.GetFootprints()
                    for pad in fp.Pads()}
        assert res.scheme == "srcdst"
        assert res.wire_count == 3
        assert pad_nets == {"/X1:1--M1:U", "/X1:2--M1:V", "/X1:3--KM1:A1"}
        assert _pad_numbers(board) == pads_before, "renumber renamed a pad"


if __name__ == "__main__":
    test_wire_names_are_applied_to_board_nets()
    test_reapplying_wire_names_never_touches_pads_and_is_stable()
    test_review_edit_after_apply_renames_the_net()
    test_renumber_reapplies_fresh_names_to_already_renamed_nets()
    print("OK wire name plugin: board nets renamed from generated wire numbers; "
          "reapply is stable and never touches pad numbers; review edits reach "
          "the board after a rename; renumber reassigns")
