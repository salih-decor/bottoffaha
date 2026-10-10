"""الخطوة 2 من المرحلة 5: تحليل محلي محدود — فحص فقط، بدون حفظ."""

import hashlib
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")


def read(fn):
    with open(os.path.join(ROOT, fn), encoding="utf-8", errors="ignore") as f:
        return f.read()


def sha(fn):
    with open(os.path.join(ROOT, fn), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_backend_untouched_vs_backup():
    import pytest

    backup_dir = os.path.join(ROOT, "backup_phase4")
    if not os.path.isdir(backup_dir):
        pytest.skip("backup_phase4 absent in clean push folder — skipping hash comparison (backups must not be uploaded)")
    for fn in ("app.py", "rounds_store.py"):
        assert sha(fn) == sha(os.path.join("backup_phase4", fn)), f"{fn} must stay unchanged in step 2"


def test_image_review_js_local_only():
    src = read("image_review.js")
    assert "ImageReview" in src
    assert "board-image-input" in src and "board-canvas" in src and "board-preview" in src
    assert "غير معروف" in src
    assert "EXPECTED_COLS = 5" in src or "EXPECTED_COLS=5" in src
    # لا رفع ولا حفظ
    assert "fetch(" not in src
    assert "XMLHttpRequest" not in src
    assert "WebSocket" not in src
    assert "localStorage" not in src
    assert "/api/rounds" not in src and "/api/import" not in src
    # قبول PNG/JPEG ومعالجة التالف
    assert "image/png" in src and "image/jpeg" in src
    assert "corrupt" in src and "invalid_type" in src
    # لا تصنيف تفاح للمغلقة
    assert "لا تصنيف تفاح" in src or "غير معروف" in src
    # لا إحداثيات ثابتة: يجب ذكر عدم الافتراض
    assert "willReadFrequently" in src or "getImageData" in src


def test_index_section_placement_and_preview():
    html = read("index.html")
    assert 'id="image-review"' in html
    assert 'id="board-image-input"' in html
    assert 'accept="image/png,image/jpeg"' in html
    assert 'id="board-preview"' in html
    assert 'id="board-canvas"' in html
    assert 'id="board-status"' in html
    assert 'id="board-cells"' in html
    assert 'src="image_review.js"' in html
    # بعد round-logger وقبل stats-panel
    assert html.index('id="round-logger"') < html.index('id="image-review"') < html.index('id="stats-panel"')
    # لا حفظ من قسم الصورة
    seg = html.split('id="image-review"')[1].split('id="stats-panel"')[0]
    assert "saveActual" not in seg and "/api/rounds" not in seg
    # الوظائف السابقة سليمة
    assert 'id="round-logger"' in html and 'id="stats-panel"' in html and "refreshStats" in html


def test_unsuitable_and_corrupt_handling_documented():
    src = read("image_review.js")
    for key in ("too_large", "columns_not_5", "rows_unclear", "low_confidence", "no_image"):
        assert key in src, f"missing unclear-case handler: {key}"


def test_reference_image_availability_noted():
    # المرجع البصري المعروض في المحادثة غير مخزن محلياً — نوثق ذلك بدل ادعاء الاختبار عليه
    import glob

    imgs = [os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "*.png")) + glob.glob(os.path.join(ROOT, "*.jpg"))]
    assert "1xbet.png" in imgs  # أيقونة واجهة فقط وليست لقطة طاولة
    # لا توجد لقطة طاولة Apple of Fortune محلية بهذا الاسم المتوقع
    assert not os.path.exists(os.path.join(ROOT, "apple-of-fortune-reference.png"))


def test_previous_store_still_works():
    import sys

    sys.path.insert(0, ROOT)
    import rounds_store

    r = rounds_store.validate_round({"user_id": "u", "session_id": 1, "row": 1, "predicted_box": 2, "actual_box": 2, "ts": 1000})
    assert r["hit"] is True
