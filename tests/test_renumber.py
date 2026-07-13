"""Scheme override + renumber-from-scratch.

The tuning loop the plugin dialog drives: a scheme picked for one run beats the
spec file's `numbering:` but never renumbers by itself (persisted numbers win);
`renumber=True` discards the store and the review table's wire_no column and
reassigns everything, while every other edited review column survives.
"""
import csv
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kicad_plugin.core import generate_harness_docs  # noqa: E402
from tests import mock_pcbnew as mock  # noqa: E402


def _store_numbers(td):
    with open(os.path.join(td, "wire_numbers.json"), encoding="utf-8") as fh:
        return json.load(fh)["numbers"]


def _review_rows(td, stem="p"):
    path = os.path.join(td, f"{stem}_wire_review.csv")
    with open(path, newline="", encoding="utf-8") as fh:
        return {row["key"]: row for row in csv.DictReader(fh)}


def _write_review(td, rows, stem="p"):
    path = os.path.join(td, f"{stem}_wire_review.csv")
    columns = list(next(iter(rows.values())).keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=columns)
        wr.writeheader()
        wr.writerows(rows.values())


def test_scheme_override_is_per_run_and_never_renumbers_by_itself():
    with tempfile.TemporaryDirectory() as td:
        res1 = generate_harness_docs(mock.sample_board(), pcbnew_module=mock,
                                     out_dir=td, stem="p", emit_wireviz=False)
        assert res1.scheme == "global"
        first = _store_numbers(td)
        assert sorted(first.values()) == ["1", "2", "3"]

        # picking a scheme without renumbering: persisted numbers win untouched
        res2 = generate_harness_docs(mock.sample_board(), pcbnew_module=mock,
                                     out_dir=td, stem="p", emit_wireviz=False,
                                     scheme="srcdst")
        assert res2.scheme == "srcdst"
        assert _store_numbers(td) == first
        assert any("for this run only" in w for w in res2.warnings), res2.warnings

        # unknown scheme names fall back to the spec's choice, with a warning
        res3 = generate_harness_docs(mock.sample_board(), pcbnew_module=mock,
                                     out_dir=td, stem="p", emit_wireviz=False,
                                     scheme="bogus")
        assert res3.scheme == "global"
        assert any("unknown numbering scheme" in w for w in res3.warnings)


def test_renumber_reassigns_and_keeps_other_review_edits():
    with tempfile.TemporaryDirectory() as td:
        generate_harness_docs(mock.sample_board(), pcbnew_module=mock,
                              out_dir=td, stem="p", emit_wireviz=False)
        first = _store_numbers(td)

        # user edits: a manual number and a note; plus a stale store entry for
        # a net that left the design (kept by normal runs, wiped by renumber)
        W1_U = "-M1:U<->X1:1"          # endpoint key of the /W1_U wire
        rows = _review_rows(td)
        rows[W1_U]["wire_no"] = "99"
        rows[W1_U]["notes"] = "twisted pair"
        _write_review(td, rows)
        store_path = os.path.join(td, "wire_numbers.json")
        data = json.load(open(store_path, encoding="utf-8"))
        data["numbers"]["/GHOST"] = "7"
        json.dump(data, open(store_path, "w", encoding="utf-8"))

        # a normal run applies the review number and keeps the ghost entry
        generate_harness_docs(mock.sample_board(), pcbnew_module=mock,
                              out_dir=td, stem="p", emit_wireviz=False)
        merged = _store_numbers(td)
        assert merged[W1_U] == "99" and merged["/GHOST"] == "7"

        # renumber: fresh endpoint-derived numbers, manual number and ghost
        # entry gone, the note survives
        res = generate_harness_docs(mock.sample_board(), pcbnew_module=mock,
                                    out_dir=td, stem="p", emit_wireviz=False,
                                    scheme="srcdst", renumber=True)
        assert res.scheme == "srcdst"
        fresh = _store_numbers(td)
        assert fresh[W1_U] == "X1:1--M1:U"
        assert fresh["-M1:V<->X1:2"] == "X1:2--M1:V"
        assert fresh["-KM1:A1<->X1:3"] == "X1:3--KM1:A1"
        assert "/GHOST" not in fresh
        rows = _review_rows(td)
        assert rows[W1_U]["wire_no"] == "X1:1--M1:U"
        assert rows[W1_U]["notes"] == "twisted pair"

        # the next normal run keeps the renumbered result stable
        generate_harness_docs(mock.sample_board(), pcbnew_module=mock,
                              out_dir=td, stem="p", emit_wireviz=False)
        assert _store_numbers(td) == fresh
        assert first != fresh


if __name__ == "__main__":
    test_scheme_override_is_per_run_and_never_renumbers_by_itself()
    test_renumber_reassigns_and_keeps_other_review_edits()
    print("OK renumber: scheme override is per-run; renumber discards store/"
          "review numbers, keeps notes, and stays stable afterwards")
