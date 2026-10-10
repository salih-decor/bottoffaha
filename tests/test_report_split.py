"""تقارير كل صف مع فاصل ثقة Wilson + فصل زمني صارم."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rounds_store


def test_wilson_ci_basic():
    lo, hi = rounds_store.wilson_ci(0, 0)
    assert lo is None and hi is None
    lo, hi = rounds_store.wilson_ci(20, 100)
    assert 0.0 <= lo < 0.2 < hi <= 1.0
    # عينة أكبر → فاصل أضيق
    lo1, hi1 = rounds_store.wilson_ci(20, 100)
    lo2, hi2 = rounds_store.wilson_ci(200, 1000)
    assert (hi2 - lo2) < (hi1 - lo1)


def test_build_report_per_row():
    rounds = []
    for i in range(10):
        rounds.append({"user_id": "u", "session_id": 1, "row": 1, "predicted_box": 1, "actual_box": 1, "hit": True, "ts": 1000 + i})
    for i in range(10):
        pred, actual = (1, 2)
        rounds.append({"user_id": "u", "session_id": 1, "row": 2, "predicted_box": pred, "actual_box": actual, "hit": False, "ts": 2000 + i})
    rep = rounds_store.build_report(rounds, baseline_p=0.2)
    assert rep["total"] == 20
    assert rep["per_row"]["1"]["attempts"] == 10
    assert rep["per_row"]["1"]["hits"] == 10
    assert rep["per_row"]["2"]["hits"] == 0
    assert rep["per_row"]["1"]["ci_low"] is not None
    assert "limits" in rep and "خط الأساس" in rep["limits"]


def test_split_temporal_and_leakage_check():
    rounds = [
        {"user_id": "u", "session_id": 1, "row": 1, "predicted_box": 1, "actual_box": 1, "hit": True, "ts": 3000},
        {"user_id": "u", "session_id": 1, "row": 1, "predicted_box": 1, "actual_box": 2, "hit": False, "ts": 1000},
        {"user_id": "u", "session_id": 1, "row": 1, "predicted_box": 1, "actual_box": 1, "hit": True, "ts": 2000},
    ]
    parts = rounds_store.split_train_test(rounds, 0.34)
    assert parts["leakage_check"]["ok"] is True
    assert parts["train"][0]["ts"] <= parts["test"][0]["ts"]
    assert "ممنوع" in parts["rule"] or "للقياس فقط" in parts["rule"]
    # تداخل مصطنع يجب كشفه
    bad = rounds_store.check_no_leakage(parts["test"], parts["train"])
    assert bad["ok"] is False
