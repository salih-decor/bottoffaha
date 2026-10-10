"""اختبار عدم ادعاء نمط على بيانات عشوائية، وقدرة الأدوات على كشف نمط حقيقي."""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rounds_store


def make_random_rounds(n, seed, baseline_p=0.2):
    """بيانات اصطناعية عشوائية معروفة: توقع وفعلي مستقلان 1-5."""
    rng = random.Random(seed)
    rounds = []
    for i in range(n):
        pred = rng.randint(1, 5)
        actual = rng.randint(1, 5)
        rounds.append(
            {
                "user_id": "syn",
                "session_id": 1,
                "row": (i % 10) + 1,
                "predicted_box": pred,
                "actual_box": actual,
                "hit": pred == actual,
                "ts": 1000 + i,
            }
        )
    return rounds


def make_pattern_rounds(n, hit_rate_target=0.6):
    """بيانات تجريبية بنمط معروف: نسبة نجاح ثابتة أعلى من خط الأساس (موزعة بالتساوي)."""
    # توزيع متساوٍ حتى يحافظ التقسيم الزمني على نفس المعدل في train و test
    # مثال 60%: نمط [hit,hit,hit,miss,miss] مكرر
    hits_per_5 = int(round(hit_rate_target * 5))
    rounds = []
    for i in range(n):
        is_hit = (i % 5) < hits_per_5
        pred, actual = (2, 2) if is_hit else (2, 4)
        rounds.append(
            {
                "user_id": "pat",
                "session_id": 1,
                "row": 3,
                "predicted_box": pred,
                "actual_box": actual,
                "hit": pred == actual,
                "ts": 5000 + i,
            }
        )
    return rounds


def test_random_data_does_not_claim_pattern():
    # n=300 عشوائي خالص ببذرة ثابتة — يجب ألا يدعي تفوقاً
    rounds = make_random_rounds(300, seed=12345)
    parts = rounds_store.split_train_test(rounds, 0.5)
    res = rounds_store.evaluate_vs_baseline(parts["test"], baseline_p=0.2)
    assert res["n"] == 150
    assert res["significant_vs_baseline"] is False
    assert "لا يوجد دليل" in res["verdict"]


def test_pattern_data_is_detected_when_present():
    # نمط حقيقي 60% على n=200 مع baseline 20% — يجب كشفه
    rounds = make_pattern_rounds(200, 0.6)
    parts = rounds_store.split_train_test(rounds, 0.5)
    res = rounds_store.evaluate_vs_baseline(parts["test"], baseline_p=0.2)
    assert res["n"] == 100
    assert abs(res["hit_rate"] - 0.6) < 1e-9
    assert res["p_value_ge"] < 0.05
    assert res["significant_vs_baseline"] is True
    # وفاصل الثقة لا يشمل خط الأساس
    assert res["ci_low"] is not None and res["ci_low"] > 0.2
