"""المرحلة 3: خط الأساس المناسب لقواعد اللعبة — ليس 20% تلقائياً."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rounds_store


def test_baseline_p_for_varies_with_safe_count():
    assert abs(rounds_store.baseline_p_for(1, 5) - 0.2) < 1e-12
    assert abs(rounds_store.baseline_p_for(4, 5) - 0.8) < 1e-12
    assert abs(rounds_store.baseline_p_for(0, 5) - 0.0) < 1e-12
    # مثال: إذا كانت الطاولة 4 آمنة من 5، فخط الأساس 80% وليس 20%
    assert rounds_store.baseline_p_for(4, 5) != rounds_store.baseline_p_for(1, 5)


def test_baseline_p_for_rejects_bad():
    import pytest

    with pytest.raises(ValueError):
        rounds_store.baseline_p_for(6, 5)
    with pytest.raises(ValueError):
        rounds_store.baseline_p_for(-1, 5)
    with pytest.raises(ValueError):
        rounds_store.baseline_p_for(1, 0)


def test_default_baseline_is_unconfirmed_assumption():
    cfg = rounds_store.get_baseline_config()
    assert cfg["num_boxes"] == 5
    # الافتراض الحالي 1 آمن من 5 — لكنه غير مؤكد
    assert cfg["confirmed"] is False
    assert "UNCONFIRMED" in cfg["source"] or "assumption" in cfg["source"].lower() or "UNCONFIRMED" in cfg.get("note", "")
    assert abs(cfg["baseline_p"] - 0.2) < 1e-12


def test_wrong_baseline_changes_verdict():
    # نفس البيانات: 80 إصابة من 100
    # مع baseline=0.2 → دال، ومع baseline=0.8 → غير دال (عند الحد)
    import rounds_store as rs

    def mk(n, hits):
        out = []
        for i in range(n):
            pred, actual = (1, 1) if i < hits else (1, 2)
            out.append({"user_id": "t", "session_id": 1, "row": 1, "predicted_box": pred, "actual_box": actual, "hit": pred == actual, "ts": 1000 + i})
        return out

    rounds = mk(100, 80)
    r20 = rs.evaluate_vs_baseline(rounds, baseline_p=0.2)
    r80 = rs.evaluate_vs_baseline(rounds, baseline_p=0.8)
    assert r20["significant_vs_baseline"] is True
    # عند 80/100 مع baseline 0.8: الحد الفاصل p≈0.5 → غير دال
    assert r80["significant_vs_baseline"] is False
