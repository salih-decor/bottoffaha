"""وحدة مستقلة لتسجيل جولات Apple of Fortune ونتائجها الفعلية.

القاعدة الأساسية: لا يوجد اتصال بـ 1xBet ولا معرفة مسبقة بمواقع التفاحات.
التسجيل يدوي من المستخدم *بعد* ظهور النتيجة، لأغراض الاختبار والإحصاء فقط.

المرحلة الثالثة:
- خط الأساس ليس 20% تلقائياً — يعتمد على عدد المربعات الآمنة فعلاً في كل صف.
- التقسيم train/test زمني صارم، ونتائج الاختبار لا تستخدم في الضبط.
- تقارير لكل صف مع فاصل ثقة Wilson 95% وتصحيح Bonferroni لتعدد المقارنات.
- تصدير/استيراد CSV مع تحقق وهجرة من السجلات القديمة.

مرحلة جودة البيانات:
- كل سجل يحفظ إعدادات اللعبة المرصودة (num_boxes/num_safe/level) — unknown إذا لم يتحقق المستخدم.
- معرف فريد round_id لمنع التكرار.
- توقيتان مميزان: predicted_at (توليد التوقع قبل اللعب) و ts (إدخال النتيجة بعد الظهور).
- لا توصف نتيجة بأنها تنبؤ ناجح إلا بوجود توقع محفوظ قبل النتيجة (prediction_verified).
- الإحصائيات مفصولة حسب مجموعة القواعد والجلسة — لا خلط.
"""

import csv
import io
import json
import math
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

# --- إعداد قواعد اللعبة: افتراض غير مؤكد حتى يثبته المستخدم من الطاولة الفعلية ---
NUM_BOXES = 5
ASSUMED_NUM_SAFE = 1  # افتراض فقط — غير مؤكد
BASELINE_P = 0.2  # للتوافق الخلفي = ASSUMED_NUM_SAFE / NUM_BOXES
BASELINE_SOURCE = "assumption: 1 safe of 5 (UNCONFIRMED — confirm from actual table)"
BASELINE_CONFIRMED = False
MIN_ROWS = 1
MAX_ROWS = 10
MIN_BOXES = 2
MAX_BOXES = 10

DEFAULT_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "rounds.jsonl")
GAME_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "game_config.json")

UNKNOWN = "unknown"


def baseline_p_for(num_safe: int, num_boxes: int = NUM_BOXES) -> float:
    """يحسب احتمال الإصابة بالتخمين العشوائي لصندوق واحد."""
    if not isinstance(num_safe, int) or not isinstance(num_boxes, int):
        raise ValueError("num_safe و num_boxes يجب أن يكونا عددين صحيحين")
    if num_boxes <= 0:
        raise ValueError("num_boxes يجب أن يكون موجباً")
    if not (0 <= num_safe <= num_boxes):
        raise ValueError("num_safe يجب أن يكون بين 0 و num_boxes")
    return num_safe / num_boxes


def get_baseline_config(config_file: str = GAME_CONFIG_FILE) -> Dict[str, Any]:
    """يرجع إعداد خط الأساس: من ملف game_config.json إن وجد، وإلا الافتراض المعلن."""
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            num_boxes = int(cfg.get("num_boxes", NUM_BOXES))
            num_safe = int(cfg.get("num_safe_per_row", ASSUMED_NUM_SAFE))
            p = baseline_p_for(num_safe, num_boxes)
            confirmed = bool(cfg.get("confirmed", False))
            src = f"config file {os.path.basename(config_file)}" + ("" if confirmed else " (UNCONFIRMED assumption)")
            return {
                "num_boxes": num_boxes,
                "num_safe_per_row": num_safe,
                "baseline_p": p,
                "source": src,
                "confirmed": confirmed,
                "note": str(cfg.get("note", "")),
            }
        except (ValueError, json.JSONDecodeError, KeyError, TypeError):
            pass
    return {
        "num_boxes": NUM_BOXES,
        "num_safe_per_row": ASSUMED_NUM_SAFE,
        "baseline_p": BASELINE_P,
        "source": BASELINE_SOURCE,
        "confirmed": BASELINE_CONFIRMED,
        "note": "UNCONFIRMED assumption — set num_safe_per_row from the actual observed table before any claim.",
    }


def calculate_experimental_hash(string_data: str) -> int:
    """FNV-1a 32-bit — نفس منطق النسخة الأصلية، لكن مصنف كتجريبي فقط."""
    hash_val = 2166136261
    for char in string_data:
        hash_val ^= ord(char)
        hash_val = (hash_val * 16777619) & 0xFFFFFFFF
    return hash_val


def predict_experimental(user_id: str, row: int, session_id: int) -> int:
    """توقع تجريبي حتمي — ليس تنبؤاً حقيقياً بنتائج 1xBet."""
    ss = f"{user_id}_{row}_{session_id}"
    return (calculate_experimental_hash(ss) % NUM_BOXES) + 1


def new_round_id() -> str:
    return uuid.uuid4().hex[:12]


def normalize_level(value: Any) -> str:
    if value is None:
        return UNKNOWN
    s = str(value).strip()
    return s if s else UNKNOWN


def parse_optional_int(value: Any) -> Optional[int]:
    """يرجع int أو None لـ unknown/فارغ. يرفع ValueError للنص غير الرقمي."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    s = str(value).strip().lower()
    if s in ("", UNKNOWN, "none", "null", "na", "n/a", "?"):
        return None
    return int(s)


def validate_round(entry: Dict[str, Any]) -> Dict[str, Any]:
    """يتحقق من الجولة ويرجع نسخة منظفة مع هجرة السجلات القديمة.

    الحقول الجديدة اختيارية للتوافق: round_id (يولد تلقائياً)،
    num_boxes/num_safe (None = unknown بدون افتراض)، level (unknown افتراضياً)،
    predicted_at (None = توقيت غير موثق → غير مؤهل كتنبؤ ناجح).
    """
    if not isinstance(entry, dict):
        raise ValueError("entry must be a dict")
    user_id = str(entry.get("user_id", "")).strip()
    if not user_id or len(user_id) < 1:
        raise ValueError("user_id مطلوب")
    try:
        session_id = int(entry.get("session_id"))
        row = int(entry.get("row"))
        predicted_box = int(entry.get("predicted_box"))
        actual_box = int(entry.get("actual_box"))
    except (TypeError, ValueError):
        raise ValueError("session_id و row و predicted_box و actual_box يجب أن تكون أرقاماً صحيحة")
    if not (MIN_ROWS <= row <= MAX_ROWS):
        raise ValueError(f"row يجب أن يكون بين {MIN_ROWS} و {MAX_ROWS}")
    if not (1 <= predicted_box <= NUM_BOXES):
        raise ValueError(f"predicted_box يجب أن يكون بين 1 و {NUM_BOXES}")
    if not (1 <= actual_box <= NUM_BOXES):
        raise ValueError(f"actual_box يجب أن يكون بين 1 و {NUM_BOXES}")

    # توقيت الإدخال (بعد الظهور) — ts للتوافق الخلفي
    raw_ts = entry.get("ts", entry.get("entered_at", int(time.time())))
    try:
        entered_at = int(raw_ts)
    except (TypeError, ValueError):
        entered_at = int(time.time())

    # توقيت التوقع (قبل اللعب) — مميز عن توقيت الإدخال
    raw_pred_at = entry.get("predicted_at", None)
    if raw_pred_at is None or (isinstance(raw_pred_at, str) and raw_pred_at.strip().lower() in ("", UNKNOWN)):
        predicted_at = None
    else:
        try:
            predicted_at = int(raw_pred_at)
        except (TypeError, ValueError):
            raise ValueError("predicted_at يجب أن يكون timestamp صحيحاً أو فارغاً")
    if predicted_at is not None and predicted_at > entered_at:
        raise ValueError("predicted_at بعد ts — التوقع يجب أن يسبق إدخال النتيجة")

    # إعدادات اللعبة المرصودة — unknown بدون افتراض
    try:
        num_boxes = parse_optional_int(entry.get("num_boxes", None))
        num_safe = parse_optional_int(entry.get("num_safe", entry.get("num_safe_per_row", None)))
    except ValueError:
        raise ValueError("num_boxes و num_safe يجب أن تكون أرقاماً أو unknown")
    if num_boxes is not None and not (MIN_BOXES <= num_boxes <= MAX_BOXES):
        raise ValueError(f"num_boxes يجب أن يكون بين {MIN_BOXES} و {MAX_BOXES} أو unknown")
    if num_boxes is not None and num_safe is not None:
        if not (0 <= num_safe <= num_boxes):
            raise ValueError("num_safe يجب أن يكون بين 0 و num_boxes")
    level = normalize_level(entry.get("level", UNKNOWN))

    round_id = str(entry.get("round_id", "") or "").strip()
    if not round_id:
        round_id = new_round_id()

    prediction_verified = bool(predicted_at is not None and predicted_at <= entered_at)
    hit = bool(predicted_box == actual_box)
    return {
        "round_id": round_id,
        "user_id": user_id,
        "session_id": session_id,
        "row": row,
        "predicted_box": predicted_box,
        "actual_box": actual_box,
        "hit": hit,
        "predicted_at": predicted_at,
        "ts": entered_at,
        "num_boxes": num_boxes,
        "num_safe": num_safe,
        "level": level,
        "prediction_verified": prediction_verified,
        "hit_verified": bool(hit and prediction_verified),
    }


def round_id_exists(round_id: str, data_file: str = DEFAULT_DATA_FILE) -> bool:
    if not round_id or not os.path.exists(data_file):
        return False
    with open(data_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(obj.get("round_id", "")) == round_id:
                return True
    return False


def append_round(entry: Dict[str, Any], data_file: str = DEFAULT_DATA_FILE) -> Dict[str, Any]:
    """يسجل جولة واحدة بعد التحقق، مع منع التكرار بنفس round_id."""
    cleaned = validate_round(entry)
    os.makedirs(os.path.dirname(os.path.abspath(data_file)), exist_ok=True)
    if round_id_exists(cleaned["round_id"], data_file):
        raise ValueError(f"duplicate round_id: {cleaned['round_id']} — الجولة مسجلة مسبقاً")
    with open(data_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
    return cleaned


def load_rounds(data_file: str = DEFAULT_DATA_FILE) -> List[Dict[str, Any]]:
    """يقرأ الجولات مع هجرة السجلات القديمة (بدون round_id/إعدادات) تلقائياً."""
    if not os.path.exists(data_file):
        return []
    rounds: List[Dict[str, Any]] = []
    with open(data_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                rounds.append(validate_round(obj))
            except ValueError:
                continue
    return rounds


def rules_key(entry: Dict[str, Any]) -> str:
    nb = entry.get("num_boxes", None)
    ns = entry.get("num_safe", None)
    lv = entry.get("level", UNKNOWN) or UNKNOWN
    return f"boxes={nb if nb is not None else UNKNOWN}|safe={ns if ns is not None else UNKNOWN}|level={lv}"


def baseline_for_entry(entry: Dict[str, Any]) -> Optional[float]:
    nb, ns = entry.get("num_boxes"), entry.get("num_safe")
    if isinstance(nb, int) and isinstance(ns, int):
        return baseline_p_for(ns, nb)
    return None


def compute_stats(rounds: List[Dict[str, Any]], baseline_p: float = BASELINE_P) -> Dict[str, Any]:
    """يحسب الإحصائيات مع فصل حسب مجموعة القواعد — يحذر عند الخلط."""
    total = len(rounds)
    hits = sum(1 for r in rounds if r.get("hit"))
    verified_hits = sum(1 for r in rounds if r.get("hit_verified"))
    verified_total = sum(1 for r in rounds if r.get("prediction_verified"))
    hit_rate = (hits / total) if total > 0 else None
    verified_rate = (verified_hits / verified_total) if verified_total else None
    per_row: Dict[int, Dict[str, Any]] = {}
    for r in rounds:
        row = int(r["row"])
        d = per_row.setdefault(row, {"total": 0, "hits": 0, "verified_total": 0, "verified_hits": 0})
        d["total"] += 1
        if r.get("hit"):
            d["hits"] += 1
        if r.get("prediction_verified"):
            d["verified_total"] += 1
            if r.get("hit"):
                d["verified_hits"] += 1
    for row, d in per_row.items():
        d["hit_rate"] = (d["hits"] / d["total"]) if d["total"] else None
        d["verified_hit_rate"] = (d["verified_hits"] / d["verified_total"]) if d["verified_total"] else None
    groups = sorted({rules_key(r) for r in rounds})
    mixed_warning = ""
    if len(groups) > 1:
        mixed_warning = f"تحذير خلط: {len(groups)} مجموعات قواعد مختلفة في نفس الإحصائية — افصلها قبل الاستنتاج: {groups[:4]}"
    if total == 0:
        sample_note = "لا توجد جولات مسجلة بعد — لا يمكن استخلاص أي نتيجة."
    elif total < 30:
        sample_note = f"عينة صغيرة جداً (n={total}) — أي نسبة نجاح غير دالة إحصائياً."
    elif total < 200:
        sample_note = f"عينة محدودة (n={total}) — النتائج استكشافية فقط."
    else:
        sample_note = f"عينة متوسطة (n={total}) — ما زالت تحتاج اختباراً مقابل خط الأساس."
    if mixed_warning:
        sample_note += " " + mixed_warning
    return {
        "total": total,
        "hits": hits,
        "misses": total - hits,
        "hit_rate": hit_rate,
        "verified_total": verified_total,
        "verified_hits": verified_hits,
        "verified_hit_rate": verified_rate,
        "per_row": per_row,
        "sample_note": sample_note,
        "groups": groups,
        "mixed_groups": len(groups) > 1,
        "baseline_p": baseline_p,
        "baseline_source": BASELINE_SOURCE,
        "baseline_confirmed": BASELINE_CONFIRMED,
        "num_boxes": NUM_BOXES,
    }


def compute_grouped_stats(rounds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """يفصل الإحصائيات حسب مجموعة القواعد والجلسة — لا خلط."""
    by_rules: Dict[str, Dict[str, Any]] = {}
    by_session: Dict[str, Dict[str, Any]] = {}
    for r in rounds:
        gk = rules_key(r)
        by_rules.setdefault(gk, []).append(r)
        sk = f"user={r.get('user_id')}|session={r.get('session_id')}|{rules_key(r)}"
        by_session.setdefault(sk, []).append(r)
    grouped = {}
    for gk, lst in by_rules.items():
        nb = lst[0].get("num_boxes")
        ns = lst[0].get("num_safe")
        bp = baseline_p_for(ns, nb) if isinstance(nb, int) and isinstance(ns, int) else None
        st = compute_stats(lst, baseline_p=bp if bp is not None else BASELINE_P)
        grouped[gk] = {"count": len(lst), "baseline_p": bp, "baseline_known": bp is not None, "stats": st}
    sessions = {k: {"count": len(v)} for k, v in by_session.items()}
    return {"by_rules": grouped, "by_session_counts": sessions, "num_groups": len(grouped)}


def binomial_p_value_ge(n: int, k: int, p: float) -> float:
    """احتمال الحصول على k نجاح أو أكثر من n محاولة (اختبار ذو طرف واحد)."""
    if n <= 0:
        return 1.0
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    total = 0.0
    for i in range(k, n + 1):
        total += math.comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i))
    return max(0.0, min(1.0, total))


def wilson_ci(hits: int, n: int, z: float = 1.96) -> Tuple[Optional[float], Optional[float]]:
    """فاصل ثقة Wilson 95% لنسبة نجاح. يرجع (None, None) إذا n=0."""
    if n <= 0:
        return (None, None)
    if hits < 0 or hits > n:
        raise ValueError("hits يجب أن يكون بين 0 و n")
    p = hits / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def check_no_leakage(train: List[Dict[str, Any]], test: List[Dict[str, Any]]) -> Dict[str, Any]:
    """يتأكد أن التقسيم زمني ولا تداخل: أقصى ts في التدريب <= أدنى ts في الاختبار."""
    if not train or not test:
        return {"ok": True, "train_max_ts": None, "test_min_ts": None, "note": "أحد الطرفين فارغ — لا تداخل."}
    train_max = max(r.get("ts", 0) for r in train)
    test_min = min(r.get("ts", 0) for r in test)
    ok = bool(train_max <= test_min)
    return {
        "ok": ok,
        "train_max_ts": train_max,
        "test_min_ts": test_min,
        "note": "فصل زمني سليم." if ok else f"TRAIN/TEST OVERLAP: train_max={train_max} > test_min={test_min}",
    }


def split_train_test(rounds: List[Dict[str, Any]], train_ratio: float = 0.5) -> Dict[str, Any]:
    """يقسم الجولات زمنياً: الأقدم للتدريب والأحدث للاختبار. الاختبار للقياس فقط."""
    if not (0.0 < train_ratio < 1.0):
        raise ValueError("train_ratio يجب أن يكون بين 0 و 1")
    ordered = sorted(rounds, key=lambda r: (r.get("ts", 0), r.get("session_id", 0), r.get("row", 0)))
    n = len(ordered)
    cut = int(n * train_ratio)
    train, test = ordered[:cut], ordered[cut:]
    leakage = check_no_leakage(train, test)
    cutoff_ts = leakage["test_min_ts"] if test else None
    return {
        "train": train,
        "test": test,
        "cutoff_ts": cutoff_ts,
        "leakage_check": leakage,
        "rule": "نتائج الاختبار للقياس فقط — ممنوع الضبط عليها. أي تعديل يعيد التقسيم والتقييم من جديد.",
    }


def evaluate_vs_baseline(
    test_rounds: List[Dict[str, Any]],
    baseline_p: float = BASELINE_P,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """يقارن بخط الأساس على جولات اختبار فقط. يستخدم hits الموثقة بالتوقيت عند توفرها."""
    n = len(test_rounds)
    hits = sum(1 for r in test_rounds if r.get("hit"))
    unverified = sum(1 for r in test_rounds if not r.get("prediction_verified", False))
    # المعيار الصارم: النجاح الموثق فقط
    vhits = sum(1 for r in test_rounds if r.get("hit_verified"))
    vn = sum(1 for r in test_rounds if r.get("prediction_verified"))
    hit_rate = (hits / n) if n else None
    verified_rate = (vhits / vn) if vn else None
    expected_hits = n * baseline_p
    p_value = binomial_p_value_ge(n, hits, baseline_p) if n else 1.0
    ci_low, ci_high = wilson_ci(hits, n) if n else (None, None)
    v_p = binomial_p_value_ge(vn, vhits, baseline_p) if vn else 1.0
    v_ci = wilson_ci(vhits, vn) if vn else (None, None)
    significant = bool(n >= 30 and p_value < alpha and (hit_rate is not None and hit_rate > baseline_p))
    if n == 0:
        verdict = "لا توجد جولات اختبار — لا يمكن الحكم."
    elif n < 30:
        verdict = f"عينة الاختبار صغيرة (n={n}) — لا حكم. سجل 30 جولة على الأقل."
    elif significant:
        verdict = f"تفوق دال ظاهرياً على خط الأساس (p={p_value:.4f}, alpha={alpha}) — يتطلب تكراراً مستقلاً قبل أي ادعاء."
    else:
        verdict = f"لا يوجد دليل على التفوق على العشوائية (p={p_value:.4f}, alpha={alpha})."
    if unverified:
        verdict += f" ملاحظة: {unverified}/{n} بدون توقيت توقع موثق — لا تحتسب كتنبؤ ناجح."
    return {
        "n": n,
        "hits": hits,
        "hit_rate": hit_rate,
        "verified_n": vn,
        "verified_hits": vhits,
        "verified_hit_rate": verified_rate,
        "verified_p_value_ge": v_p,
        "verified_ci_low": v_ci[0],
        "verified_ci_high": v_ci[1],
        "ci_low": ci_low,
        "ci_high": ci_high,
        "baseline_p": baseline_p,
        "baseline_source": BASELINE_SOURCE,
        "baseline_confirmed": BASELINE_CONFIRMED,
        "expected_hits": expected_hits,
        "p_value_ge": p_value,
        "alpha": alpha,
        "significant_vs_baseline": significant,
        "verdict": verdict,
    }


def build_report(rounds: List[Dict[str, Any]], baseline_p: float = BASELINE_P, alpha: float = 0.05) -> Dict[str, Any]:
    """تقرير كل صف مع تصحيح Bonferroni وشروط الصلاحية — بدون خلط مجموعات."""
    stats = compute_stats(rounds, baseline_p=baseline_p)
    grouped = compute_grouped_stats(rounds)
    rows_present = sorted(stats["per_row"].keys())
    m_tests = len(rows_present)
    alpha_corrected = (alpha / m_tests) if m_tests else alpha
    overall_eval = evaluate_vs_baseline(rounds, baseline_p=baseline_p, alpha=alpha)
    per_row_report: Dict[str, Dict[str, Any]] = {}
    for row_key in rows_present:
        d = stats["per_row"][row_key]
        n, h = d["total"], d["hits"]
        ci_low, ci_high = wilson_ci(h, n)
        ev_raw = evaluate_vs_baseline([r for r in rounds if int(r["row"]) == int(row_key)], baseline_p=baseline_p, alpha=alpha)
        ev_corr = evaluate_vs_baseline([r for r in rounds if int(r["row"]) == int(row_key)], baseline_p=baseline_p, alpha=alpha_corrected)
        per_row_report[str(row_key)] = {
            "row": int(row_key),
            "attempts": n,
            "hits": h,
            "hit_rate": d["hit_rate"],
            "verified_attempts": d["verified_total"],
            "verified_hits": d["verified_hits"],
            "verified_hit_rate": d["verified_hit_rate"],
            "ci_low": ci_low,
            "ci_high": ci_high,
            "p_value_ge": ev_raw["p_value_ge"],
            "p_value_vs_corrected_alpha": ev_corr["p_value_ge"],
            "alpha_corrected_bonferroni": alpha_corrected,
            "significant_raw": ev_raw["significant_vs_baseline"],
            "significant_corrected": ev_corr["significant_vs_baseline"],
            "note": "n<30: غير دال" if n < 30 else ("دال بعد تصحيح Bonferroni" if ev_corr["significant_vs_baseline"] else ("دال ظاهرياً قبل التصحيح فقط" if ev_raw["significant_vs_baseline"] else "لا دليل على التفوق")),
        }
    validity = (
        "شروط الصلاحية: (1) خط أساس معروف من الطاولة (num_safe/num_boxes مؤكدان). "
        "(2) n>=30 لكل استنتاج. (3) محاولات مستقلة بدون تسجيل انتقائي وبتسجيل متتالي كامل. "
        "(4) فصل train/test زمني وعدم الضبط على الاختبار. "
        f"(5) تصحيح تعدد المقارنات: {m_tests} اختبارات → alpha المصحح={alpha_corrected:.4f} (Bonferroni). "
        "(6) النجاح الموثق بالتوقيت فقط (predicted_at<=ts) يحتسب كتنبؤ."
    )
    limits = (
        "حدود الاستنتاج: (1) خط الأساس افتراض غير مؤكد حتى تثبت عدد المربعات الآمنة من الطاولة. "
        "(2) عينات صغيرة لا تسمح بأي ادعاء. (3) التقييم على الاختبار فقط — الضبط على الاختبار يبطل النتيجة. "
        "(4) خلط مجموعات قواعد مختلفة يبطل المتوسط — انظر by_rules. "
        "(5) النجاح على الاصطناعية يثبت عمل الأدوات فقط وليس قابلية التنبؤ باللعبة. "
        "(6) لا تنبؤ بالمستقبل بدون تكرار مستقل."
    )
    if stats["mixed_groups"]:
        limits += f" تحذير: البيانات الحالية مخلوطة ({stats['groups']}) — قيم الإجمالي غير صالحة للاستنتاج."
    return {
        "total": stats["total"],
        "hits": stats["hits"],
        "hit_rate": stats["hit_rate"],
        "verified_total": stats["verified_total"],
        "verified_hits": stats["verified_hits"],
        "verified_hit_rate": stats["verified_hit_rate"],
        "baseline_p": baseline_p,
        "baseline_source": BASELINE_SOURCE,
        "baseline_confirmed": BASELINE_CONFIRMED,
        "overall": overall_eval,
        "per_row": per_row_report,
        "m_tests": m_tests,
        "alpha": alpha,
        "alpha_corrected_bonferroni": alpha_corrected,
        "multiple_comparison_method": "bonferroni",
        "by_rules": {k: {"count": v["count"], "baseline_p": v["baseline_p"], "baseline_known": v["baseline_known"]} for k, v in grouped["by_rules"].items()},
        "sample_note": stats["sample_note"],
        "validity_conditions": validity,
        "limits": limits,
    }


CSV_FIELDS_V2 = ["round_id", "user_id", "session_id", "row", "predicted_box", "actual_box", "num_boxes", "num_safe", "level", "predicted_at", "ts"]
CSV_FIELDS_OLD = ["user_id", "session_id", "row", "predicted_box", "actual_box", "ts"]


def export_csv(rounds: List[Dict[str, Any]]) -> str:
    """يصدر بصيغة V2 مع الحفاظ على قراءة القديمة عند الاستيراد."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS_V2)
    w.writeheader()
    for r in rounds:
        c = validate_round(r)
        w.writerow(
            {
                "round_id": c["round_id"],
                "user_id": c["user_id"],
                "session_id": c["session_id"],
                "row": c["row"],
                "predicted_box": c["predicted_box"],
                "actual_box": c["actual_box"],
                "num_boxes": "" if c["num_boxes"] is None else c["num_boxes"],
                "num_safe": "" if c["num_safe"] is None else c["num_safe"],
                "level": c["level"],
                "predicted_at": "" if c["predicted_at"] is None else c["predicted_at"],
                "ts": c["ts"],
            }
        )
    return buf.getvalue()


def import_csv(text: str) -> Dict[str, Any]:
    """يستورد V2 والقديمة (هجرة تلقائية)، مع كشف التكرار داخل الملف."""
    imported: List[Dict[str, Any]] = []
    errors: List[str] = []
    skipped = 0
    try:
        reader = csv.DictReader(io.StringIO(text))
    except Exception as e:
        return {"rounds": [], "imported": 0, "skipped": 0, "errors": [f"CSV parse error: {e}"]}
    if reader.fieldnames is None:
        return {"rounds": [], "imported": 0, "skipped": 0, "errors": ["CSV فارغ أو بدون ترويسة"]}
    fields = [f.strip() for f in (reader.fieldnames or [])]
    is_old = set(CSV_FIELDS_OLD).issubset(set(fields)) and "round_id" not in fields
    is_new = "round_id" in fields and "user_id" in fields
    if not (is_old or is_new):
        return {"rounds": [], "imported": 0, "skipped": 0, "errors": [f"ترويسة غير معروفة: {fields} — المطلوب {CSV_FIELDS_V2} أو {CSV_FIELDS_OLD}"]}
    seen_ids = set()
    for i, row in enumerate(reader, start=2):
        try:
            if is_old:
                entry = {
                    "user_id": str(row.get("user_id", "")).strip(),
                    "session_id": int(str(row.get("session_id", "")).strip()),
                    "row": int(str(row.get("row", "")).strip()),
                    "predicted_box": int(str(row.get("predicted_box", "")).strip()),
                    "actual_box": int(str(row.get("actual_box", "")).strip()),
                    "ts": int(str(row.get("ts", "")).strip() or int(time.time())),
                }
            else:
                entry = {
                    "round_id": str(row.get("round_id", "") or "").strip() or new_round_id(),
                    "user_id": str(row.get("user_id", "")).strip(),
                    "session_id": int(str(row.get("session_id", "")).strip()),
                    "row": int(str(row.get("row", "")).strip()),
                    "predicted_box": int(str(row.get("predicted_box", "")).strip()),
                    "actual_box": int(str(row.get("actual_box", "")).strip()),
                    "num_boxes": str(row.get("num_boxes", "") or ""),
                    "num_safe": str(row.get("num_safe", "") or ""),
                    "level": str(row.get("level", "") or UNKNOWN),
                    "predicted_at": str(row.get("predicted_at", "") or ""),
                    "ts": int(str(row.get("ts", "")).strip() or int(time.time())),
                }
                # تطبيع الفارغ إلى unknown/None عبر validate
                if isinstance(entry.get("num_boxes"), str) and not entry["num_boxes"].strip():
                    entry["num_boxes"] = None
                if isinstance(entry.get("num_safe"), str) and not entry["num_safe"].strip():
                    entry["num_safe"] = None
                if isinstance(entry.get("predicted_at"), str) and not entry["predicted_at"].strip():
                    entry["predicted_at"] = None
            cleaned = validate_round(entry)
            if cleaned["round_id"] in seen_ids:
                raise ValueError(f"duplicate round_id داخل الملف: {cleaned['round_id']}")
            seen_ids.add(cleaned["round_id"])
            imported.append(cleaned)
        except (ValueError, TypeError, AttributeError) as e:
            skipped += 1
            errors.append(f"سطر {i}: {e}")
    return {"rounds": imported, "imported": len(imported), "skipped": skipped, "errors": errors}


def append_many(rounds: List[Dict[str, Any]], data_file: str = DEFAULT_DATA_FILE) -> Dict[str, Any]:
    """يسجل دفعة مع منع التكرار (داخل الدفعة وضد الملف)."""
    ok, bad = 0, 0
    errs: List[str] = []
    seen = set()
    for i, r in enumerate(rounds):
        try:
            c = validate_round(r)
            if c["round_id"] in seen:
                raise ValueError(f"duplicate round_id داخل الدفعة: {c['round_id']}")
            seen.add(c["round_id"])
            append_round(c, data_file)
            ok += 1
        except ValueError as e:
            bad += 1
            errs.append(f"index {i}: {e}")
    return {"appended": ok, "skipped": bad, "errors": errs}
