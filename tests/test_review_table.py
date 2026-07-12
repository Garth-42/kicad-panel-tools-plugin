"""Editable wire review CSV workflow."""
import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tests.mock_pcbnew as mock  # noqa: E402
from kicad_plugin.core import generate_harness_docs  # noqa: E402
from harness.review import load_review  # noqa: E402


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_plugin_writes_and_reloads_review_table():
    with tempfile.TemporaryDirectory() as td:
        board = mock.sample_board()
        r1 = generate_harness_docs(board, pcbnew_module=mock, out_dir=td,
                                   stem="p", emit_wireviz=False)
        review = os.path.join(td, "p_wire_review.csv")
        assert review in r1.outputs and os.path.exists(review)
        rows = _rows(review)
        assert {"key", "wire_no", "from_ref", "to_ref", "notes"} <= set(rows[0])

        rows[0]["wire_no"] = "FIELD-201"
        rows[0]["notes"] = "installer checks label"
        with open(review, "w", newline="", encoding="utf-8") as fh:
            wr = csv.DictWriter(fh, fieldnames=rows[0].keys())
            wr.writeheader(); wr.writerows(rows)

        r2 = generate_harness_docs(board, pcbnew_module=mock, out_dir=td,
                                   stem="p", emit_wireviz=False)
        csv_text = open(os.path.join(td, "p_wirelist.csv"), encoding="utf-8").read()
        assert "FIELD-201" in csv_text
        assert "installer checks label" in csv_text
        assert review in r2.outputs
        assert any(row["wire_no"] == "FIELD-201" and
                   row["notes"] == "installer checks label"
                   for row in _rows(review))


def test_review_loader_warns_on_bad_rows():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "review.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            fh.write("key,wire_no\n,1\n/A,2\n/A,3\n")
        rows, warnings = load_review(path)
        assert rows["/A"]["wire_no"] == "3"
        assert len(warnings) == 2, warnings


if __name__ == "__main__":
    test_plugin_writes_and_reloads_review_table()
    test_review_loader_warns_on_bad_rows()
    print("OK review table: generated, reloads edits, preserves notes, warns")
