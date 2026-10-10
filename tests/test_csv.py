"""تصدير واستيراد CSV مع التحقق."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rounds_store


def sample_rounds():
    return [
        {"user_id": "u1", "session_id": 1, "row": 1, "predicted_box": 2, "actual_box": 2, "hit": True, "ts": 1000},
        {"user_id": "u1", "session_id": 1, "row": 2, "predicted_box": 3, "actual_box": 5, "hit": False, "ts": 1001},
    ]


def test_export_import_roundtrip():
    rounds = sample_rounds()
    text = rounds_store.export_csv(rounds)
    # صيغة V2 مع توافق قراءة القديمة
    assert "round_id" in text and "predicted_at" in text and "level" in text
    parsed = rounds_store.import_csv(text)
    assert parsed["imported"] == 2
    assert parsed["skipped"] == 0
    assert len(parsed["rounds"]) == 2
    assert parsed["rounds"][0]["hit"] is True


def test_import_rejects_bad_rows_but_keeps_good():
    text = (
        "user_id,session_id,row,predicted_box,actual_box,ts\n"
        "u1,1,1,2,2,1000\n"
        "u1,1,99,2,2,1001\n"  # row خارج النطاق
        "u1,1,2,9,2,1002\n"  # صندوق خارج النطاق
        ",1,2,2,2,1003\n"  # بدون user
    )
    parsed = rounds_store.import_csv(text)
    assert parsed["imported"] == 1
    assert parsed["skipped"] == 3
    assert len(parsed["errors"]) == 3


def test_import_rejects_missing_columns():
    parsed = rounds_store.import_csv("user_id,session_id\nx,1\n")
    assert parsed["imported"] == 0
    assert parsed["errors"]
