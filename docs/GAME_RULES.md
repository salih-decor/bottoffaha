# قواعد اللعبة وخط الأساس — تحقق مطلوب

## ما هو مؤكد من الكود
- الواجهة تعرض 5 مربعات في كل صف (`index.html:buildMatrix` — شبكة `grid-cols-5`).
- المتنبئ التجريبي يختار صندوقاً واحداً من 5 (`rounds_store.predict_experimental`).

## ما هو غير مؤكد
- عدد المربعات الآمنة فعلاً في صف Apple of Fortune على 1xBet يختلف حسب إعدادات الطاولة/المخاطرة.
- أمثلة:
  - 1 آمن من 5 → تخمين عشوائي لصندوق واحد يصيب بنسبة 20%.
  - 4 آمنة من 5 (شائع في وضع القنبلة الواحدة) → نفس التخمين يصيب بنسبة 80%.
- لذلك 20% ليست حقيقة تلقائية — هي افتراض `game_config.json` (`num_safe_per_row=1`, `confirmed=false`).

## المطلوب من المستخدم قبل أي استنتاج
1. افتح طاولة Apple of Fortune الفعلية ولاحظ عدد التفاحات مقابل القنابل في الصف.
2. حدث `game_config.json`: ضع `num_safe_per_row` الصحيح، ولا تضع `confirmed=true` إلا بعد مشاهدة جولات حقيقية.
3. مرر `baseline_p` المناسب لكل تقييم: `baseline_p_for(num_safe, num_boxes)`.
4. اختبار `test_wrong_baseline_changes_verdict` يثبت أن نفس البيانات (80/100) دالة مع baseline=0.2 وغير دالة مع baseline=0.8 — أي خطأ في خط الأساس يقلب الحكم.

## القاعدة المطبقة في الكود
- كل `/api/predict` و `/api/stats` و `/api/report` ترجع `baseline_p` مع `baseline_source` و `baseline_confirmed`.
- الواجهة تعرض تحذيراً دائماً: افتراض غير مؤكد حتى التأكيد.
