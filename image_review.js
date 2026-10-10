/* مراجعة صورة محلية للعبة Apple of Fortune — فحص فقط.
 * يعمل داخل المتصفح فقط: لا رفع للخادم، لا حفظ تلقائي، لا تخمين للمغلقة.
 * أي شك => الحالة «غير معروف».
 */
(function () {
  "use strict";

  var EXPECTED_COLS = 5;
  var MAX_ANALYZE_WIDTH = 640;
  var MAX_FILE_BYTES = 8 * 1024 * 1024;
  var MIN_CONFIDENCE = 0.6;

  var state = { status: "idle", reason: "", rows: 0, cols: 0, cells: [], confidence: 0 };

  function $(id) { return document.getElementById(id); }

  function setStatus(msg) {
    var el = $("board-status");
    if (el) el.textContent = msg;
  }

  function setCellsInfo(cells, rows, cols) {
    var box = $("board-cells");
    if (!box) return;
    box.innerHTML = "";
    if (!cells || !cells.length) {
      box.innerHTML = "<div>لا توجد خلايا مؤكدة — الحالة: غير معروف.</div>";
      return;
    }
    var head = document.createElement("div");
    head.textContent = "تم تحديد الشبكة: " + rows + " صفوف × " + cols + " أعمدة (" + cells.length + " خلية). محتوى المربعات المغلقة غير معروف — لا تصنيف تفاح.";
    box.appendChild(head);
    cells.slice(0, 50).forEach(function (c, i) {
      var d = document.createElement("div");
      d.textContent = "خلية " + (i + 1) + ": صف " + c.row + " / عمود " + c.col + " — مركز (" + Math.round(c.x) + "," + Math.round(c.y) + ")";
      box.appendChild(d);
    });
    if (cells.length > 50) {
      var more = document.createElement("div");
      more.textContent = "… (+" + (cells.length - 50) + " خلية)";
      box.appendChild(more);
    }
  }

  function fail(reason, msg) {
    state = { status: "unknown", reason: reason, rows: 0, cols: 0, cells: [], confidence: 0 };
    setStatus(msg || "تعذر تحديد الشبكة بثقة — الحالة: غير معروف.");
    setCellsInfo([], 0, 0);
    drawOverlay(null);
    return state;
  }

  // لون خشبي داكن للمربعات الدائرية: بني محمر على خلفية داكنة
  function isWood(r, g, b) {
    return r >= 100 && g >= 55 && g <= 175 && b <= 110 && r > g && g > b && (r - b) > 35;
  }

  function smooth(arr, w) {
    var out = new Array(arr.length).fill(0);
    for (var i = 0; i < arr.length; i++) {
      var s = 0, c = 0;
      for (var k = -w; k <= w; k++) {
        var j = i + k;
        if (j >= 0 && j < arr.length) { s += arr[j]; c++; }
      }
      out[i] = s / Math.max(1, c);
    }
    return out;
  }

  function findPeaks(proj, minDist, thresholdRatio) {
    var max = 0;
    for (var i = 0; i < proj.length; i++) if (proj[i] > max) max = proj[i];
    if (max <= 0) return [];
    var thr = max * thresholdRatio;
    var cands = [];
    for (var x = 1; x < proj.length - 1; x++) {
      if (proj[x] >= thr && proj[x] >= proj[x - 1] && proj[x] > proj[x + 1]) cands.push({ pos: x, val: proj[x] });
    }
    cands.sort(function (a, b) { return b.val - a.val; });
    var kept = [];
    cands.forEach(function (c) {
      var ok = true;
      for (var k = 0; k < kept.length; k++) {
        if (Math.abs(kept[k].pos - c.pos) < minDist) { ok = false; break; }
      }
      if (ok) kept.push(c);
    });
    kept.sort(function (a, b) { return a.pos - b.pos; });
    return kept;
  }

  function spacingCV(peaks) {
    if (peaks.length < 3) return 0;
    var gaps = [];
    for (var i = 1; i < peaks.length; i++) gaps.push(peaks[i].pos - peaks[i - 1].pos);
    var mean = gaps.reduce(function (a, b) { return a + b; }, 0) / gaps.length;
    if (mean <= 0) return 1;
    var sd = Math.sqrt(gaps.reduce(function (a, g) { return a + (g - mean) * (g - mean); }, 0) / gaps.length);
    return sd / mean;
  }

  function analyzePixels(data, w, h) {
    // قناع خشبي على كتل 4×4 لتقليل الضجيج
    var bw = Math.ceil(w / 4), bh = Math.ceil(h / 4);
    var mask = new Array(bw * bh).fill(0);
    for (var by = 0; by < bh; by++) {
      for (var bx = 0; bx < bw; bx++) {
        var brown = 0, tot = 0;
        for (var dy = 0; dy < 4; dy++) {
          for (var dx = 0; dx < 4; dx++) {
            var px = bx * 4 + dx, py = by * 4 + dy;
            if (px >= w || py >= h) continue;
            var o = (py * w + px) * 4;
            tot++;
            if (isWood(data[o], data[o + 1], data[o + 2])) brown++;
          }
        }
        mask[by * bw + bx] = (tot > 0 && brown / tot >= 0.4) ? 1 : 0;
      }
    }
    // إسقاط عمودي في الشريط الأوسط (يتجاوز مؤشرات الصفوف اليسرى والترويسة)
    var x0 = Math.floor(bw * 0.18), x1 = Math.floor(bw * 0.98);
    var y0 = Math.floor(bh * 0.12), y1 = Math.floor(bh * 0.92);
    var vproj = new Array(x1 - x0).fill(0);
    for (var y = y0; y < y1; y++) {
      for (var x = x0; x < x1; x++) vproj[x - x0] += mask[y * bw + x];
    }
    var minColDist = Math.max(4, Math.floor((x1 - x0) / (EXPECTED_COLS * 2)));
    var colPeaks = findPeaks(smooth(vproj, 2), minColDist, 0.55);
    if (colPeaks.length !== EXPECTED_COLS) {
      return { ok: false, reason: "columns_not_5", detail: "الأعمدة المكتشفة: " + colPeaks.length + " (المطلوب 5)" };
    }
    if (spacingCV(colPeaks) > 0.25) {
      return { ok: false, reason: "columns_irregular", detail: "تباعد الأعمدة غير منتظم" };
    }
    // إسقاط أفقي ضمن نطاق الأعمدة — عدد الصفوف غير مفترض
    var hproj = new Array(y1 - y0).fill(0);
    var cx0 = x0 + colPeaks[0].pos, cx1 = x0 + colPeaks[colPeaks.length - 1].pos;
    for (var yy = y0; yy < y1; yy++) {
      for (var xx = cx0; xx <= cx1; xx++) hproj[yy - y0] += mask[yy * bw + xx];
    }
    var minRowDist = Math.max(4, Math.floor((y1 - y0) / 24));
    var rowPeaks = findPeaks(smooth(hproj, 2), minRowDist, 0.5);
    if (rowPeaks.length < 2) {
      return { ok: false, reason: "rows_unclear", detail: "الصفوف المكتشفة: " + rowPeaks.length };
    }
    if (rowPeaks.length >= 3 && spacingCV(rowPeaks) > 0.3) {
      return { ok: false, reason: "rows_irregular", detail: "تباعد الصفوف غير منتظم" };
    }
    var colMean = colPeaks.reduce(function (a, p) { return a + p.val; }, 0) / colPeaks.length;
    var colMax = Math.max.apply(null, vproj);
    var rowMean = rowPeaks.reduce(function (a, p) { return a + p.val; }, 0) / rowPeaks.length;
    var confidence = Math.min(1, (colMean / Math.max(1, colMax)) * 0.6 + (rowPeaks.length >= 3 ? 0.25 : 0.15) + (spacingCV(colPeaks) < 0.15 ? 0.15 : 0.05));
    if (confidence < MIN_CONFIDENCE) {
      return { ok: false, reason: "low_confidence", detail: "الثقة " + confidence.toFixed(2) };
    }
    var sx = w / bw, sy = h / bh;
    var cells = [];
    rowPeaks.forEach(function (rp, ri) {
      colPeaks.forEach(function (cp, ci) {
        cells.push({ row: ri + 1, col: ci + 1, x: (x0 + cp.pos) * sx, y: (y0 + rp.pos) * sy });
      });
    });
    return {
      ok: true, cols: EXPECTED_COLS, rows: rowPeaks.length, cells: cells, confidence: confidence,
      bounds: { x0: cx0 * sx, x1: cx1 * sx, y0: (y0 + rowPeaks[0].pos) * sy, y1: (y0 + rowPeaks[rowPeaks.length - 1].pos) * sy }
    };
  }

  function drawOverlay(result) {
    var cv = $("board-canvas");
    if (!cv) return;
    var ctx = cv.getContext("2d");
    var img = $("board-preview");
    if (!img || !img.naturalWidth) return;
    var scale = Math.min(1, MAX_ANALYZE_WIDTH / img.naturalWidth);
    cv.width = Math.round(img.naturalWidth * scale);
    cv.height = Math.round(img.naturalHeight * scale);
    ctx.drawImage(img, 0, 0, cv.width, cv.height);
    if (!result || !result.ok) return;
    var kx = cv.width / img.naturalWidth, ky = cv.height / img.naturalHeight;
    ctx.strokeStyle = "#22d3ee";
    ctx.lineWidth = 2;
    ctx.strokeRect(result.bounds.x0 * kx, result.bounds.y0 * ky, (result.bounds.x1 - result.bounds.x0) * kx, (result.bounds.y1 - result.bounds.y0) * ky);
    ctx.fillStyle = "#f59e0b";
    result.cells.forEach(function (c) {
      ctx.beginPath();
      ctx.arc(c.x * kx, c.y * ky, 5, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  function analyzeCurrent() {
    var img = $("board-preview");
    if (!img || !img.naturalWidth) {
      return fail("no_image", "اختر صورة أولاً — الحالة: غير معروف.");
    }
    try {
      var scale = Math.min(1, MAX_ANALYZE_WIDTH / img.naturalWidth);
      var tmp = document.createElement("canvas");
      tmp.width = Math.max(1, Math.round(img.naturalWidth * scale));
      tmp.height = Math.max(1, Math.round(img.naturalHeight * scale));
      var tctx = tmp.getContext("2d", { willReadFrequently: true });
      tctx.drawImage(img, 0, 0, tmp.width, tmp.height);
      var d = tctx.getImageData(0, 0, tmp.width, tmp.height);
      var res = analyzePixels(d.data, tmp.width, tmp.height);
      if (!res.ok) {
        return fail(res.reason, "تعذر تحديد الشبكة بثقة (" + res.detail + ") — الحالة: غير معروف. جرّب لقطة أوضح كاملة للشبكة.");
      }
      state = { status: "grid_found", reason: "", rows: res.rows, cols: res.cols, cells: res.cells, confidence: res.confidence };
      setStatus("تم تحديد الشبكة: " + res.rows + " صفوف × " + res.cols + " أعمدة بثقة " + res.confidence.toFixed(2) + ". محتوى المربعات المغلقة غير معروف — لا تصنيف تفاح في هذه الخطوة ولا حفظ.");
      setCellsInfo(res.cells, res.rows, res.cols);
      drawOverlay(res);
      return state;
    } catch (e) {
      return fail("analysis_error", "تعذر تحليل الصورة (ملف تالف؟) — الحالة: غير معروف.");
    }
  }

  function clearAll() {
    var inp = $("board-image-input");
    if (inp) inp.value = "";
    var img = $("board-preview");
    if (img) { img.removeAttribute("src"); img.classList.add("hidden"); }
    var cv = $("board-canvas");
    if (cv) { var ctx = cv.getContext("2d"); ctx.clearRect(0, 0, cv.width, cv.height); }
    fail("cleared", "اختر صورة PNG أو JPEG لمعاينتها وتحليل شبكتها محلياً.");
    state = { status: "idle", reason: "", rows: 0, cols: 0, cells: [], confidence: 0 };
  }

  function handleFile(file) {
    if (!file) return fail("no_image", "اختر صورة أولاً — الحالة: غير معروف.");
    var validTypes = ["image/png", "image/jpeg"];
    if (validTypes.indexOf(file.type) === -1) {
      return fail("invalid_type", "نوع غير مدعوم (المقبول PNG و JPEG فقط) — الحالة: غير معروف.");
    }
    if (file.size > MAX_FILE_BYTES) {
      return fail("too_large", "الصورة أكبر من 8MB — الحالة: غير معروف.");
    }
    var url = URL.createObjectURL(file);
    var img = $("board-preview");
    img.classList.remove("hidden");
    img.onload = function () {
      URL.revokeObjectURL(url);
      setStatus("تم تحميل المعاينة محلياً (بدون رفع). اضغط «تحليل الشبكة محلياً».");
      drawOverlay(null);
      state = { status: "loaded", reason: "", rows: 0, cols: 0, cells: [], confidence: 0 };
      setCellsInfo([], 0, 0);
    };
    img.onerror = function () {
      URL.revokeObjectURL(url);
      fail("corrupt", "تعذر قراءة الصورة (ملف تالف؟) — الحالة: غير معروف.");
    };
    img.src = url;
    return state;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var inp = $("board-image-input");
    if (inp) inp.addEventListener("change", function (ev) { handleFile(ev.target.files[0]); });
    var btn = $("board-analyze-btn");
    if (btn) btn.addEventListener("click", analyzeCurrent);
    var clr = $("board-clear-btn");
    if (clr) clr.addEventListener("click", clearAll);
  });

  window.ImageReview = { handleFile: handleFile, analyzeCurrent: analyzeCurrent, clearAll: clearAll, state: function () { return state; } };
})();
