"""يتأكد أن /api/predict تجريبي ولا يحتوي ثقة وهمية."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app


def test_generate_smart_box_range_and_deterministic():
    a = app.generate_smart_box("12345", 2, 1)
    b = app.generate_smart_box("12345", 2, 1)
    assert a == b
    assert 1 <= a <= 5


def test_no_random_confidence_in_source():
    src = open(os.path.join(os.path.dirname(__file__), "..", "app.py"), encoding="utf-8").read()
    assert "import random" not in src
    assert "confidence_rate" not in src
    assert "confidence" not in src.lower() or "الثقة الوهمية" in src  # فقط تعليق الإزالة مسموح
    assert "experimental" in src
    assert "/api/rounds" in src
    assert "/api/stats" in src


def test_phase3_endpoints_present():
    src = open(os.path.join(os.path.dirname(__file__), "..", "app.py"), encoding="utf-8").read()
    assert "/api/report" in src
    assert "/api/export" in src
    assert "/api/import" in src
    assert "baseline_confirmed" in src
    assert "get_baseline_config" in src


def test_no_1xbet_connection_claim():
    import pathlib

    for fn in ["app.py", "rounds_store.py", "index.html"]:
        p = pathlib.Path(os.path.join(os.path.dirname(__file__), "..", fn))
        if p.exists():
            t = p.read_text(encoding="utf-8", errors="ignore").lower()
            assert "https://1xbet" not in t
            assert "1xbet api" not in t
    # لا توليد تنبؤات من غير مسجل: predict_experimental حتمية ولا تقرأ نتائج مستقبلية
    import rounds_store

    assert rounds_store.predict_experimental("a", 1, 1) in (1, 2, 3, 4, 5)


def test_data_quality_fields_present():
    import pathlib

    rs = pathlib.Path(os.path.join(os.path.dirname(__file__), "..", "rounds_store.py")).read_text(encoding="utf-8")
    assert "round_id" in rs
    assert "predicted_at" in rs
    assert "prediction_verified" in rs
    assert "bonferroni" in rs.lower()
    assert "unknown" in rs.lower()
    assert "duplicate round_id" in rs
    app_src = pathlib.Path(os.path.join(os.path.dirname(__file__), "..", "app.py")).read_text(encoding="utf-8")
    assert "grouped" in app_src
    idx = pathlib.Path(os.path.join(os.path.dirname(__file__), "..", "index.html")).read_text(encoding="utf-8")
    assert "round-logger" in idx and "predicted_at" in idx
    assert "بدون تخطي" in idx or "متتالية" in idx


def test_http_helpers():
    req = "GET /api/predict?row=3&user_id=abc&session_id=2 HTTP/1.1\nHost: x\n"
    assert app.get_path(req) == "/api/predict"
    assert app.get_method(req) == "GET"
    assert app.get_query_param(req, "row") == "3"
    assert app.extract_json_body("POST /x HTTP/1.1\r\nContent-Length: 2\r\n\r\n{}") == {}
