"""اختبار المقارنة بخط الأساس العشوائي (1/5 = 20%) على جولات اختبار فقط."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rounds_store


def make_rounds(n, hits, start_ts=1000):
    rounds = []
    for i in range(n):
        pred, actual = (1, 1) if i < hits else (1, 2)
        rounds.append(
            {
                "user_id": "t",
                "session_id": 1,
                "row": (i % 10) + 1,
                "predicted_box": pred,
                "actual_box": actual,
                "hit": pred == actual,
                "ts": start_ts + i,
            }
        )
    return rounds


def test_baseline_random_is_20_percent():
    assert abs(rounds_store.BASELINE_P - 0.2) < 1e-12
    assert rounds_store.NUM_BOXES == 5


def test_evaluate_no_evidence_on_small_sample():
    rounds = make_rounds(10, 4)  # 40% ظاهرياً لكن n صغيرة
    res = rounds_store.evaluate_vs_baseline(rounds)
    assert res["n"] == 10
    assert res["significant_vs_baseline"] is False
    assert "صغيرة" in res["verdict"]


def test_evaluate_no_evidence_when_at_baseline():
    rounds = make_rounds(100, 20)  # exactly baseline
    res = rounds_store.evaluate_vs_baseline(rounds)
    assert res["significant_vs_baseline"] is False
    assert res["p_value_ge"] > 0.05


def test_split_prevents_leakage():
    rounds = make_rounds(10, 5)
    parts = rounds_store.split_train_test(rounds, 0.5)
    assert len(parts["train"]) == 5
    assert len(parts["test"]) == 5
    # الأحدث في الاختبار
    assert parts["test"][0]["ts"] >= parts["train"][-1]["ts"]
    # التقييم يستخدم الاختبار فقط
    res = rounds_store.evaluate_vs_baseline(parts["test"])
    assert res["n"] == 5


def test_binomial_p_value_sane():
    # 30 إصابة من 100 عند p=0.2 مستحيل تقريباً -> p صغير
    p = rounds_store.binomial_p_value_ge(100, 30, 0.2)
    assert p < 0.05
    # 0 إصابات -> p=1
    assert rounds_store.binomial_p_value_ge(10, 0, 0.2) == 1.0
