"""Native review-dialog CSV helper checks."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kicad_plugin.review_dialog import _read_csv, _write_csv  # noqa: E402


def test_native_editor_csv_helpers_round_trip():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "review.csv")
        columns = ["key", "wire_no", "notes"]
        _write_csv(path, columns, [{"key": "/A", "wire_no": "101", "notes": "field"}])
        rows, got_columns = _read_csv(path)
        assert got_columns == columns
        assert rows == [{"key": "/A", "wire_no": "101", "notes": "field"}]


if __name__ == "__main__":
    test_native_editor_csv_helpers_round_trip()
    print("OK review dialog: CSV helpers round-trip")
