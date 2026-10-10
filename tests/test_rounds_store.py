import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rounds_store


def test_predict_experimental_deterministic():
    a = rounds_store.predict_experimental("12345", 1, 1)
    b = rounds_store.predict_experimental("12345", 1, 1)
    assert a == b
    assert 1 <= a <= 5


def test_predict_differs_across_inputs_sometimes():
    vals = {rounds_store.predict_experimental(f"u{i}", (i % 10) + 1, 1) for i in range(20)}
    assert len(vals) > 1


def test_validate_round_ok():
    r = rounds_store.validate_round({"user_id": "99", "session_id": 1, "row": 3, "predicted_box": 2, "actual_box": 2})
    assert r["hit"] is True
    r2 = rounds_store.validate_round({"user_id": "99", "session_id": 1, "row": 3, "predicted_box": 2, "actual_box": 4})
    assert r2["hit"] is False


def test_validate_round_rejects_bad():
    import pytest

    with pytest.raises(ValueError):
        rounds_store.validate_round({"user_id": "", "session_id": 1, "row": 1, "predicted_box": 1, "actual_box": 1})
    with pytest.raises(ValueError):
        rounds_store.validate_round({"user_id": "x", "session_id": 1, "row": 11, "predicted_box": 1, "actual_box": 1})
    with pytest.raises(ValueError):
        rounds_store.validate_round({"user_id": "x", "session_id": 1, "row": 1, "predicted_box": 6, "actual_box": 1})


def test_append_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        fp = os.path.join(td, "rounds.jsonl")
        rounds_store.append_round({"user_id": "abc", "session_id": 2, "row": 1, "predicted_box": 1, "actual_box": 3}, fp)
        rounds_store.append_round({"user_id": "abc", "session_id": 2, "row": 2, "predicted_box": 3, "actual_box": 3}, fp)
        rows = rounds_store.load_rounds(fp)
        assert len(rows) == 2
        stats = rounds_store.compute_stats(rows)
        assert stats["total"] == 2
        assert stats["hits"] == 1
        assert abs(stats["hit_rate"] - 0.5) < 1e-9
        assert stats["per_row"][1]["total"] == 1
        assert stats["per_row"][2]["hits"] == 1


def test_compute_stats_empty():
    stats = rounds_store.compute_stats([])
    assert stats["total"] == 0
    assert stats["hit_rate"] is None
    assert "لا توجد" in stats["sample_note"]
