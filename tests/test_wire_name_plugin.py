import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kicad_plugin.core import apply_wire_names_to_board  # noqa: E402
from tests import mock_pcbnew as mock  # noqa: E402


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


if __name__ == "__main__":
    test_wire_names_are_applied_to_board_nets()
    print("OK wire name plugin: board nets renamed from generated wire numbers")
