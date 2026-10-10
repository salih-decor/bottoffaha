"""جودة البيانات: هجرة القديمة، منع التكرار، unknown، توقيتان، فصل المجموعات، Bonferroni."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rounds_store


def old_record():
    return {"user_id": "u", "session_id": 1, "row": 2, "predicted_box": 3, "actual_box": 3, "ts": 1000}


def test_migration_old_record_gets_defaults():
    c = rounds_store.validate_round(old_record())
    assert c["round_id"] and len(c["round_id"]) >= 6
    assert c["num_boxes"] is None
    assert c["num_safe"] is None
    assert c["level"] == "unknown"
    assert c["predicted_at"] is None
    assert c["prediction_verified"] is False
    assert c["hit"] is True
    assert c["hit_verified"] is False  # لا يوصف كتنبؤ ناجح بدون توقيت مسبق


def test_unknown_settings_not_assumed():
    c = rounds_store.validate_round({**old_record(), "num_boxes": "", "num_safe": "", "level": ""})
    assert c["num_boxes"] is None and c["num_safe"] is None and c["level"] == "unknown"
    assert rounds_store.baseline_for_entry(c) is None


def test_known_settings_baseline():
    c = rounds_store.validate_round({**old_record(), "num_boxes": 5, "num_safe": 4, "level": "easy"})
    assert rounds_store.baseline_for_entry(c) == 0.8


def test_unique_id_and_dedup():
    with tempfile.TemporaryDirectory() as td:
        fp = os.path.join(td, "r.jsonl")
        e = {**old_record(), "round_id": "abc123", "predicted_at": 999, "ts": 1000}
        rounds_store.append_round(e, fp)
        try:
            rounds_store.append_round(e, fp)
            assert False, "duplicate should raise"
        except ValueError as ve:
            assert "duplicate" in str(ve).lower()
        assert len(rounds_store.load_rounds(fp)) == 1


def test_predicted_after_entered_rejected():
    import pytest

    with pytest.raises(ValueError):
        rounds_store.validate_round({**old_record(), "predicted_at": 2000, "ts": 1000})


def test_grouped_stats_no_mixing():
    a = rounds_store.validate_round({**old_record(), "round_id": "a1", "num_boxes": 5, "num_safe": 1, "level": "easy", "predicted_at": 999, "ts": 1000})
    b = rounds_store.validate_round({**old_record(), "round_id": "b1", "num_boxes": 5, "num_safe": 4, "level": "easy", "predicted_at": 999, "ts": 1001})
    st = rounds_store.compute_stats([a, b])
    assert st["mixed_groups"] is True
    assert "تحذير خلط" in st["sample_note"] or "خلط" in st["sample_note"]
    g = rounds_store.compute_grouped_stats([a, b])
    assert g["num_groups"] == 2
    rep = rounds_store.build_report([a, b])
    assert "مخلوطة" in rep["limits"] or "مخلوط" in rep["limits"]


def test_bonferroni_correction():
    rounds = []
    for row in range(1, 11):
        for i in range(30):
            hit = (i < 12)  # 40% لكل صف — دال ظاهرياً مع 0.2 قبل التصحيح ل n=30؟
            rounds.append({"user_id": "u", "session_id": 1, "row": row, "predicted_box": 1, "actual_box": 1 if hit else 2, "hit": hit, "ts": 1000 + row * 100 + i, "predicted_at": 999, "round_id": f"r{row}-{i}"})
    rep = rounds_store.build_report(rounds, baseline_p=0.2)
    assert rep["m_tests"] == 10
    assert abs(rep["alpha_corrected_bonferroni"] - 0.005) < 1e-9
    assert rep["multiple_comparison_method"] == "bonferroni"
    assert "Bonferroni" in rep["validity_conditions"]


def test_csv_old_migration_and_new_roundtrip():
    old_csv = "user_id,session_id,row,predicted_box,actual_box,ts\nu1,1,1,2,2,1000\nu1,1,2,3,5,1001\n"
    parsed = rounds_store.import_csv(old_csv)
    assert parsed["imported"] == 2
    assert all(r["level"] == "unknown" for r in parsed["rounds"])
    new_text = rounds_store.export_csv(parsed["rounds"])
    assert "round_id" in new_text and "num_safe" in new_text and "predicted_at" in new_text
    reparsed = rounds_store.import_csv(new_text)
    assert reparsed["imported"] == 2


def test_csv_duplicate_inside_file_rejected():
    rid = "dup001"
    text = (
        "round_id,user_id,session_id,row,predicted_box,actual_box,num_boxes,num_safe,level,predicted_at,ts\n"
        f"{rid},u,1,1,1,1,5,1,easy,999,1000\n"
        f"{rid},u,1,1,1,1,5,1,easy,999,1000\n"
    )
    parsed = rounds_store.import_csv(text)
    assert parsed["imported"] == 1
    assert parsed["skipped"] == 1
