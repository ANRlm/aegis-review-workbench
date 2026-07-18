(function () {
  "use strict";

  var state = {
    health: null,
    stats: null,
    jobs: [],
    selectedJobId: null,
    selectedJob: null,
    report: null,
    pollTimeout: null,
    pollAbort: null,
    selectedFile: null,
  };

  var STATUS_LABELS = {
    created: "已创建",
    queued: "排队中",
    running: "分析中",
    completed: "已完成",
    failed: "失败",
  };

  var DECISION_LABELS = {
    pass: "通过",
    review: "待复核",
    reject: "不通过",
  };

  var dom = {};

  function cacheDom() {
    dom.healthBadges = document.getElementById("health-badges");
    dom.modelNotice = document.getElementById("model-notice");
    dom.statTotal = document.getElementById("stat-total");
    dom.statPass = document.getElementById("stat-pass");
    dom.statReview = document.getElementById("stat-review");
    dom.statReject = document.getElementById("stat-reject");
    dom.statFailed = document.getElementById("stat-failed");
    dom.projectName = document.getElementById("project-name");
    dom.dropZone = document.getElementById("drop-zone");
    dom.dropText = document.getElementById("drop-text");
    dom.fileInput = document.getElementById("file-input");
    dom.btnUpload = document.getElementById("btn-upload");
    dom.uploadError = document.getElementById("upload-error");
    dom.statusFilter = document.getElementById("status-filter");
    dom.taskList = document.getElementById("task-list");
    dom.evidenceEmpty = document.getElementById("evidence-empty");
    dom.evidenceLoading = document.getElementById("evidence-loading");
    dom.evidenceLoadingText = document.getElementById("evidence-loading-text");
    dom.evidenceFailed = document.getElementById("evidence-failed");
    dom.evidenceFailedMsg = document.getElementById("evidence-failed-message");
    dom.evidenceContent = document.getElementById("evidence-content");
    dom.evidenceAssetType = document.getElementById("evidence-asset-type");
    dom.evidenceAssetName = document.getElementById("evidence-asset-name");
    dom.evidenceStatusBadge = document.getElementById("evidence-status-badge");
    dom.assetPreview = document.getElementById("asset-preview");
    dom.detectionSummary = document.getElementById("detection-summary");
    dom.detectionGrid = document.getElementById("detection-grid");
    dom.evidenceFrames = document.getElementById("evidence-frames");
    dom.framesGrid = document.getElementById("frames-grid");
    dom.reviewPlaceholder = document.getElementById("review-placeholder");
    dom.reviewContent = document.getElementById("review-content");
    dom.reviewAutoDecision = document.getElementById("review-auto-decision");
    dom.reviewFinalDecision = document.getElementById("review-final-decision");
    dom.reviewForm = document.getElementById("review-form");
    dom.decisionOptions = document.getElementById("decision-options");
    dom.reviewerName = document.getElementById("reviewer-name");
    dom.reviewNote = document.getElementById("review-note");
    dom.reviewFeedback = document.getElementById("review-feedback");
    dom.btnSaveReview = document.getElementById("btn-save-review");
    dom.downloadSection = document.getElementById("download-section");
    dom.btnDownloadJson = document.getElementById("btn-download-json");
    dom.btnDownloadCsv = document.getElementById("btn-download-csv");
    dom.btnDownloadZip = document.getElementById("btn-download-zip");
    dom.btnRetry = document.getElementById("btn-retry");
    dom.confirmDialog = document.getElementById("confirm-dialog");
    dom.confirmMessage = document.getElementById("confirm-message");
    dom.btnCancel = document.getElementById("btn-cancel");
    dom.btnConfirm = document.getElementById("btn-confirm");
  }

  var confirmResolve = null;
  var BASE = "/api";

  function apiUrl(path) {
    return BASE + path;
  }

  function assertOk(payload, response) {
    if (!payload || payload.ok !== true) {
      var msg = (payload && payload.error && payload.error.message) || "请求失败 (" + (response ? response.status : "?") + ")";
      throw new Error(msg);
    }
    return payload;
  }

  function apiFetch(path, options) {
    var opts = options || {};
    if (state.pollAbort) opts.signal = state.pollAbort.signal;
    return fetch(apiUrl(path), opts).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok) {
          var errMsg = (payload && payload.error && payload.error.message) || "HTTP " + response.status;
          throw new Error(errMsg);
        }
        return assertOk(payload, response);
      }).catch(function (err) {
        if (err instanceof SyntaxError) {
          if (!response.ok) throw new Error("HTTP " + response.status);
          throw err;
        }
        throw err;
      });
    });
  }

  function fetchHealth() {
    return apiFetch("/health").then(function (data) {
      state.health = data;
      renderHealth();
      return data;
    });
  }

  function fetchStats() {
    return apiFetch("/stats").then(function (data) {
      state.stats = data.stats;
      renderStats();
      return data;
    }).catch(function () {
      state.stats = null;
      renderStats();
    });
  }

  function fetchJobs(status) {
    var qs = status ? "?status=" + encodeURIComponent(status) : "";
    return apiFetch("/jobs" + qs).then(function (data) {
      state.jobs = data.jobs || [];
      renderJobs();
      return data;
    });
  }

  function fetchJob(jobId) {
    return apiFetch("/jobs/" + encodeURIComponent(jobId)).then(function (data) {
      return data.job || data;
    });
  }

  function fetchReport(jobId) {
    return apiFetch("/jobs/" + encodeURIComponent(jobId) + "/report").then(function (data) {
      return data.report;
    });
  }

  function createJob(formData) {
    return apiFetch("/jobs", { method: "POST", body: formData });
  }

  function analyzeJob(jobId) {
    return apiFetch("/jobs/" + encodeURIComponent(jobId) + "/analyze", { method: "POST" });
  }

  function deleteJobApi(jobId) {
    return apiFetch("/jobs/" + encodeURIComponent(jobId), { method: "DELETE" });
  }

  function reviewJobApi(jobId, payload) {
    return apiFetch("/jobs/" + encodeURIComponent(jobId) + "/review", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  }

  function artifactUrl(jobId, filename) {
    return BASE + "/jobs/" + encodeURIComponent(jobId) + "/artifacts/" + encodeURIComponent(filename);
  }

  /* ---- Numeric parsing ---- */
  function parseNumeric(value, defaultValue) {
    if (value === "" || value === null || value === undefined) return defaultValue;
    var num = Number(value);
    if (!isFinite(num)) return defaultValue;
    return num;
  }

  /* ---- Rendering ---- */
  function renderHealth() {
    if (!state.health) { dom.healthBadges.innerHTML = ""; renderModelNotice(); return; }
    var h = state.health;
    dom.healthBadges.innerHTML =
      '<span class="health-badge"><span class="health-dot ' + (h.status === "ok" ? "ok" : "warn") + '"></span>服务正常</span>' +
      '<span class="health-badge"><span class="health-dot ' + (h.model_ready ? "ok" : "warn") + '"></span>模型' + (h.model_ready ? "就绪" : "未就绪") + '</span>' +
      '<span class="health-badge"><span class="health-dot ' + (h.ffmpeg_ready ? "ok" : "warn") + '"></span>FFmpeg' + (h.ffmpeg_ready ? "就绪" : "未就绪") + '</span>';
    renderModelNotice();
  }

  function renderModelNotice() {
    var ready = state.health && state.health.model_ready === true;
    if (dom.modelNotice) {
      dom.modelNotice.hidden = ready;
    }
    updateUploadButton();
  }

  function renderStats() {
    var s = state.stats;
    dom.statTotal.textContent = s ? s.total : "-";
    dom.statPass.textContent = s ? s.pass : "-";
    dom.statReview.textContent = s ? s.review : "-";
    dom.statReject.textContent = s ? s.reject : "-";
    dom.statFailed.textContent = s ? s.failed : "-";
  }

  function renderJobs() {
    dom.taskList.innerHTML = "";
    if (state.jobs.length === 0) {
      dom.taskList.innerHTML = '<div class="empty-state">暂无任务</div>';
      return;
    }
    state.jobs.forEach(function (job) {
      var item = document.createElement("div");
      item.className = "task-item" + (job.job_id === state.selectedJobId ? " selected" : "");
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", job.job_id === state.selectedJobId ? "true" : "false");
      item.setAttribute("data-job-id", job.job_id);
      item.tabIndex = 0;
      var statusClass = "task-status " + job.status + (job.status === "running" ? " pulse-ring" : "");
      var assetName = job.asset_name || "";
      item.innerHTML =
        '<div class="task-item-top">' +
        '<span class="task-asset-name" title="' + escapeHtml(assetName) + '">' + escapeHtml(assetName) + '</span>' +
        '<span class="' + statusClass + '">' + (STATUS_LABELS[job.status] || job.status) + '</span>' +
        '</div>' +
        '<div class="task-item-meta">' +
        '<span>' + escapeHtml(job.project_name || "") + '</span>' +
        '<span>' + formatTime(job.created_at) + '</span>' +
        '<button class="task-delete-btn" data-delete="' + escapeHtml(job.job_id) + '" aria-label="删除任务 ' + escapeHtml(assetName) + '" title="删除">&times;</button>' +
        '</div>';
      item.addEventListener("click", function (e) {
        if (e.target.closest("[data-delete]")) {
          e.stopPropagation();
          handleDelete(e.target.closest("[data-delete]").getAttribute("data-delete"));
          return;
        }
        selectJob(job.job_id);
      });
      item.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          if (e.target.closest("[data-delete]")) {
            e.preventDefault();
            e.stopPropagation();
            handleDelete(e.target.closest("[data-delete]").getAttribute("data-delete"));
            return;
          }
          e.preventDefault();
          selectJob(job.job_id);
        }
      });
      dom.taskList.appendChild(item);
    });
  }

  function formatTime(isoStr) {
    if (!isoStr) return "";
    try {
      var match = isoStr.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);
      if (match) return match[1] + " " + match[2];
      return isoStr.substring(0, 16);
    } catch (_) { return isoStr; }
  }

  function escapeHtml(str) {
    var map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return String(str).replace(/[&<>"']/g, function (c) { return map[c]; });
  }

  /* ---- Evidence Panel ---- */
  function showEvidenceState(stateName) {
    dom.evidenceEmpty.hidden = true;
    dom.evidenceLoading.hidden = true;
    dom.evidenceFailed.hidden = true;
    dom.evidenceContent.hidden = true;
    if (stateName === "empty") dom.evidenceEmpty.hidden = false;
    else if (stateName === "loading") dom.evidenceLoading.hidden = false;
    else if (stateName === "failed") dom.evidenceFailed.hidden = false;
    else if (stateName === "content") dom.evidenceContent.hidden = false;
  }

  function renderEvidenceContent(job) {
    if (!job) return;
    dom.evidenceAssetType.textContent = job.asset_type === "video" ? "视频" : "图片";
    dom.evidenceAssetName.textContent = job.asset_name || "";
    dom.evidenceAssetName.title = job.asset_name || "";
    renderAssetPreview(job);
    if (!state.report) {
      dom.detectionSummary.hidden = true;
      dom.evidenceFrames.hidden = true;
    } else {
      renderDetections(state.report);
      renderEvidenceFrames(state.report, job.job_id);
    }

    dom.evidenceStatusBadge.removeAttribute("style");
    dom.evidenceStatusBadge.className = "status-badge";

    if (job.status === "running" || job.status === "queued") {
      dom.evidenceStatusBadge.classList.add("status-running");
      dom.evidenceStatusBadge.textContent = STATUS_LABELS[job.status] || job.status;
    } else if (job.status === "created") {
      dom.evidenceStatusBadge.classList.add("status-created");
      dom.evidenceStatusBadge.textContent = "待分析";
    } else if (job.status === "completed" && state.report) {
      var dec = state.report.final_decision || state.report.auto_decision;
      dom.evidenceStatusBadge.classList.add(dec || "");
      dom.evidenceStatusBadge.textContent = DECISION_LABELS[dec] || dec || "-";
    }

    var existingBtn = document.getElementById("btn-analyze-created");
    if (existingBtn) existingBtn.remove();
    if (job.status === "created") {
      var analyzeBtn = document.createElement("button");
      analyzeBtn.id = "btn-analyze-created";
      analyzeBtn.className = "btn btn-primary";
      analyzeBtn.textContent = "开始分析";
      analyzeBtn.style.marginTop = "12px";
      var modelReady = state.health && state.health.model_ready === true;
      if (!modelReady) analyzeBtn.disabled = true;
      analyzeBtn.addEventListener("click", handleRetry);
      dom.evidenceContent.appendChild(analyzeBtn);
    }
  }

  function renderAssetPreview(job) {
    if (!job || !job.asset_url) { dom.assetPreview.innerHTML = ""; return; }
    if (job.asset_type === "image") {
      dom.assetPreview.innerHTML = '<img src="' + escapeHtml(job.asset_url) + '" alt="' + escapeHtml(job.asset_name || "素材") + '" loading="lazy">';
    } else {
      dom.assetPreview.innerHTML = '<video src="' + escapeHtml(job.asset_url) + '" controls preload="metadata" class="preview-video"></video>';
    }
  }

  function renderDetections(report) {
    if (!report) return;
    var detections = report.detections || [];
    if (detections.length === 0) {
      dom.detectionSummary.hidden = false;
      dom.detectionGrid.innerHTML = '<div class="detection-none">未检测到规则目标</div>';
      return;
    }
    var byClass = {};
    detections.forEach(function (d) {
      var name = d.class_name || "未知";
      if (!byClass[name]) byClass[name] = { count: 0, maxConf: 0 };
      byClass[name].count++;
      if (d.confidence > byClass[name].maxConf) byClass[name].maxConf = d.confidence;
    });
    dom.detectionSummary.hidden = false;
    dom.detectionGrid.innerHTML = "";
    Object.keys(byClass).forEach(function (cls) {
      var item = byClass[cls];
      var el = document.createElement("div");
      el.className = "detection-item";
      el.innerHTML = '<div class="detection-class">' + escapeHtml(cls) + '</div>' +
        '<div class="detection-count">' + item.count + ' 次</div>' +
        '<div class="detection-max">最高置信度: ' + (item.maxConf * 100).toFixed(1) + '%</div>';
      dom.detectionGrid.appendChild(el);
    });
  }

  function renderEvidenceFrames(report, jobId) {
    if (!report) return;
    var frames = report.evidence_frames || [];
    if (frames.length === 0) { dom.evidenceFrames.hidden = true; return; }
    dom.evidenceFrames.hidden = false;
    dom.framesGrid.innerHTML = "";
    var detections = report.detections || [];
    var detByFrame = {};
    detections.forEach(function (d) {
      if (!detByFrame[d.frame_index]) detByFrame[d.frame_index] = [];
      detByFrame[d.frame_index].push(d);
    });
    frames.forEach(function (filename) {
      var frameIdx = null;
      var match = filename.match(/frame_(\d+)/);
      if (match) frameIdx = parseInt(match[1], 10);
      var dets = detByFrame[frameIdx] || [];
      var topDet = null;
      dets.forEach(function (d) { if (!topDet || d.confidence > topDet.confidence) topDet = d; });
      var card = document.createElement("div");
      card.className = "frame-card";
      card.innerHTML = '<img src="' + escapeHtml(artifactUrl(jobId, filename)) + '" alt="证据帧" loading="lazy">' +
        '<div class="frame-card-info">' +
        (topDet ? '<span class="frame-card-time">' + (topDet.timestamp_seconds != null ? topDet.timestamp_seconds.toFixed(1) + "s" : "-") + ' &middot; ' + escapeHtml(topDet.class_name || "") + '</span>' +
         '<span>置信度: ' + (topDet.confidence * 100).toFixed(1) + '%</span>' : '<span class="frame-card-time">证据帧</span>') +
        '</div>';
      dom.framesGrid.appendChild(card);
    });
  }

  /* ---- Review Panel ---- */
  function renderReviewPanel() {
    if (!state.selectedJob) { dom.reviewPlaceholder.hidden = false; dom.reviewContent.hidden = true; dom.downloadSection.hidden = true; return; }
    var job = state.selectedJob;
    if (job.status !== "completed") { dom.reviewPlaceholder.hidden = false; dom.reviewContent.hidden = true; dom.downloadSection.hidden = true; return; }
    dom.reviewPlaceholder.hidden = true;
    dom.reviewContent.hidden = false;
    if (state.report) {
      var autoDec = state.report.auto_decision;
      var finalDec = state.report.final_decision;
      dom.reviewAutoDecision.textContent = DECISION_LABELS[autoDec] || autoDec || "-";
      dom.reviewAutoDecision.className = "decision-value " + (autoDec || "");
      dom.reviewFinalDecision.textContent = DECISION_LABELS[finalDec] || finalDec || "-";
      dom.reviewFinalDecision.className = "decision-value " + (finalDec || "");
      var radios = dom.decisionOptions.querySelectorAll('input[name="decision"]');
      radios.forEach(function (r) { r.checked = r.value === finalDec; });
      dom.reviewerName.value = state.report.reviewer || "";
      dom.reviewNote.value = state.report.note || "";
      dom.reviewForm.disabled = false;
      if (state.report.downloads) dom.downloadSection.hidden = false;
    } else {
      dom.reviewForm.disabled = true;
      dom.downloadSection.hidden = true;
    }
  }

  /* ---- Job Selection & Polling ---- */
  function selectJob(jobId) {
    cancelPolling();
    state.selectedJobId = jobId;
    state.selectedJob = null;
    state.report = null;
    renderJobs();
    showEvidenceState("loading");
    dom.evidenceLoadingText.textContent = "加载中…";
    dom.reviewPlaceholder.hidden = false;
    dom.reviewContent.hidden = true;
    dom.downloadSection.hidden = true;
    fetchJob(jobId).then(function (job) {
      if (state.selectedJobId !== jobId) return;
      state.selectedJob = job;
      var status = job.status;
      if (status === "completed") {
        return fetchReport(jobId).then(function (report) {
          if (state.selectedJobId !== jobId) return;
          state.report = report;
          showEvidenceState("content");
          renderEvidenceContent(job);
          renderReviewPanel();
        });
      } else if (status === "failed") {
        showEvidenceState("failed");
        dom.evidenceFailedMsg.textContent = job.error || "任务执行失败。";
        dom.btnRetry.textContent = "重新分析";
        updateRetryButton();
        renderReviewPanel();
      } else if (status === "created") {
        showEvidenceState("content");
        renderEvidenceContent(job);
        renderReviewPanel();
      } else {
        showEvidenceState("content");
        renderEvidenceContent(job);
        renderReviewPanel();
        startPolling(jobId);
      }
    }).catch(function (err) {
      if (state.selectedJobId !== jobId) return;
      showEvidenceState("failed");
      dom.evidenceFailedMsg.textContent = err.message || "无法加载任务。";
    });
  }

  function pollJob(jobId, token) {
    var abort = new AbortController();
    state.pollAbort = abort;
    state.pollTimeout = setTimeout(function () {
      state.pollAbort = null;
      state.pollTimeout = null;
      if (state.selectedJobId !== jobId) return;
      apiFetch("/jobs/" + encodeURIComponent(jobId), { signal: abort.signal }).then(function (data) {
        var job = data.job || data;
        if (state.selectedJobId !== jobId) return;
        state.selectedJob = job;
        if (job.status === "completed") {
          return fetchReport(jobId).then(function (report) {
            if (state.selectedJobId !== jobId) return;
            state.report = report;
            showEvidenceState("content");
            renderEvidenceContent(job);
            renderReviewPanel();
            fetchStats();
            fetchJobs(dom.statusFilter.value || undefined);
          });
        } else if (job.status === "failed") {
          showEvidenceState("failed");
          dom.evidenceFailedMsg.textContent = job.error || "任务执行失败。";
          renderReviewPanel();
          fetchStats();
          fetchJobs(dom.statusFilter.value || undefined);
        } else {
          showEvidenceState("content");
          renderEvidenceContent(job);
          renderJobs();
          pollJob(jobId, token);
        }
      }).catch(function (err) {
        if (state.selectedJobId !== jobId) return;
        showEvidenceState("failed");
        dom.evidenceFailedMsg.textContent = err.message || "轮询失败，请检查网络连接后重试。";
      });
    }, 1000);
  }

  function startPolling(jobId) {
    cancelPolling();
    var token = {};
    pollJob(jobId, token);
    state._pollToken = token;
  }

  function cancelPolling() {
    if (state.pollTimeout) { clearTimeout(state.pollTimeout); state.pollTimeout = null; }
    if (state.pollAbort) { state.pollAbort.abort(); state.pollAbort = null; }
    state._pollToken = null;
  }

  /* ---- Upload ---- */
  function handleUpload() {
    var projectName = dom.projectName.value.trim();
    if (!projectName || projectName.length > 80) { dom.uploadError.textContent = "请输入 1–80 字的项目名称。"; return; }
    if (!state.selectedFile) { dom.uploadError.textContent = "请选择审核素材。"; return; }
    if (!state.health || state.health.model_ready !== true) {
      dom.uploadError.textContent = "模型未就绪，暂时无法创建并分析任务。";
      return;
    }
    dom.btnUpload.disabled = true;
    dom.uploadError.textContent = "";
    var formData = new FormData();
    formData.append("asset", state.selectedFile);
    formData.append("project_name", projectName);
    var settings = buildSettings();
    if (settings) {
      try { formData.append("settings", JSON.stringify(settings)); } catch (_) { dom.uploadError.textContent = "规则设置格式不正确。"; dom.btnUpload.disabled = false; return; }
    }
    createJob(formData).then(function (data) {
      var jobId = data.job.job_id;
      return analyzeJob(jobId).then(function () { return jobId; });
    }).then(function (jobId) {
      dom.uploadError.textContent = "";
      resetUploadForm();
      return fetchJobs(dom.statusFilter.value || undefined).then(function () { return fetchStats(); }).then(function () { return jobId; });
    }).then(function (jobId) {
      selectJob(jobId);
      toast("任务已创建，正在分析…");
    }).catch(function (err) {
      dom.uploadError.textContent = err.message || "上传失败，请重试。";
      updateUploadButton();
    });
  }

  function buildSettings() {
    function fieldValue(id) { return document.getElementById(id) ? document.getElementById(id).value : ""; }
    return {
      risk_classes: (function () {
        var raw = (document.getElementById("setting-risk-classes") ? document.getElementById("setting-risk-classes").value : "").trim();
        var items = raw ? raw.split(",").map(function (s) { return s.trim(); }).filter(Boolean) : [];
        return items.length ? items : ["enemy"];
      })(),
      reject_confidence: parseNumeric(fieldValue("setting-reject-conf"), 0.60),
      review_confidence: parseNumeric(fieldValue("setting-review-conf"), 0.35),
      inference_confidence: parseNumeric(fieldValue("setting-inference-conf"), 0.25),
      min_evidence_frames: 1,
      sample_interval_seconds: parseNumeric(fieldValue("setting-sample-interval"), 1.0),
      max_sample_frames: parseInt(fieldValue("setting-max-frames"), 10) || 120,
    };
  }

  function resetUploadForm() {
    dom.projectName.value = "";
    state.selectedFile = null;
    dom.fileInput.value = "";
    dom.dropZone.classList.remove("file-selected");
    dom.dropText.textContent = "拖放或点击上传素材";
    updateUploadButton();
  }

  /* ---- Delete ---- */
  function handleDelete(jobId) {
    confirmDialog("确认删除此任务？删除后不可恢复。").then(function (confirmed) {
      if (!confirmed) return;
      deleteJobApi(jobId).then(function () {
        if (state.selectedJobId === jobId) {
          state.selectedJobId = null; state.selectedJob = null; state.report = null;
          showEvidenceState("empty");
          dom.reviewPlaceholder.hidden = false; dom.reviewContent.hidden = true; dom.downloadSection.hidden = true;
        }
        return fetchJobs(dom.statusFilter.value || undefined);
      }).then(function () { return fetchStats(); }).then(function () { toast("任务已删除。"); }).catch(function (err) { toast(err.message || "删除失败。", true); });
    });
  }

  /* ---- Review ---- */
  function handleSaveReview() {
    if (!state.selectedJobId || !state.selectedJob) return;
    var jobId = state.selectedJobId;
    var checkedRadio = dom.decisionOptions.querySelector('input[name="decision"]:checked');
    if (!checkedRadio) { dom.reviewFeedback.textContent = "请选择审核结论。"; dom.reviewFeedback.className = "review-feedback error"; return; }
    var decision = checkedRadio.value;
    var reviewer = dom.reviewerName.value.trim();
    if (!reviewer || reviewer.length > 40) { dom.reviewFeedback.textContent = "请填写负责人（1–40 字）。"; dom.reviewFeedback.className = "review-feedback error"; return; }
    var note = dom.reviewNote.value.trim() || null;
    dom.btnSaveReview.disabled = true;
    dom.reviewFeedback.textContent = "";
    dom.reviewFeedback.className = "review-feedback";
    reviewJobApi(jobId, { decision: decision, reviewer: reviewer, note: note }).then(function (data) {
      state.report = data.report || data;
      renderReviewPanel();
      renderEvidenceContent(state.selectedJob);
      return fetchStats();
    }).then(function () { return fetchJobs(dom.statusFilter.value || undefined); }).then(function () {
      dom.reviewFeedback.textContent = "改判已保存。";
      dom.reviewFeedback.className = "review-feedback";
      toast("审核结论已更新。");
    }).catch(function (err) {
      dom.reviewFeedback.textContent = err.message || "保存失败。";
      dom.reviewFeedback.className = "review-feedback error";
      toast(err.message || "保存失败。", true);
    }).finally(function () { dom.btnSaveReview.disabled = false; });
  }

  /* ---- Downloads ---- */
  function validateDownloadUrl(url, jobId) {
    try {
      var u = new URL(url, window.location.origin);
      if (u.origin !== window.location.origin) return false;
      var expected = "/api/jobs/" + encodeURIComponent(jobId) + "/artifacts/";
      return u.pathname.indexOf(expected) === 0;
    } catch (_) { return false; }
  }

  function handleDownloadJson() {
    if (!state.selectedJobId) return;
    if (!state.report) { toast("报告尚未加载。", true); return; }
    var blob = new Blob([JSON.stringify(state.report, null, 2)], { type: "application/json" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "report_" + state.selectedJobId + ".json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function handleDownloadCsv() {
    if (!state.selectedJobId || !state.report) { toast("报告尚未加载。", true); return; }
    var downloads = state.report.downloads;
    if (!downloads || !downloads.csv) { toast("CSV 文件不可用。", true); return; }
    var url = downloads.csv;
    if (!validateDownloadUrl(url, state.selectedJobId)) { toast("CSV 下载地址无效。", true); return; }
    window.location.assign(url);
  }

  function handleDownloadZip() {
    if (!state.selectedJobId || !state.report) { toast("报告尚未加载。", true); return; }
    var downloads = state.report.downloads;
    if (!downloads || !downloads.zip) { toast("ZIP 文件不可用。", true); return; }
    var url = downloads.zip;
    if (!validateDownloadUrl(url, state.selectedJobId)) { toast("ZIP 下载地址无效。", true); return; }
    window.location.assign(url);
  }

  function updateRetryButton() {
    var modelReady = state.health && state.health.model_ready === true;
    dom.btnRetry.disabled = !modelReady;
  }

  function handleRetry() {
    if (!state.selectedJobId) return;
    var jobId = state.selectedJobId;
    if (!state.health || state.health.model_ready !== true) { toast("模型尚未就绪，无法分析。", true); return; }
    analyzeJob(jobId).then(function () { return fetchJob(jobId); }).then(function (job) {
      if (state.selectedJobId !== jobId) return;
      state.selectedJob = job;
      showEvidenceState("content");
      renderEvidenceContent(job);
      renderReviewPanel();
      startPolling(jobId);
      fetchJobs(dom.statusFilter.value || undefined);
      toast("已重新提交分析。");
    }).catch(function (err) { toast(err.message || "重新分析失败。", true); });
  }

  /* ---- Toast ---- */
  var toastTimer = null;
  function toast(message, isError) {
    var existing = document.querySelector(".toast");
    if (existing) existing.remove();
    if (toastTimer) clearTimeout(toastTimer);
    var el = document.createElement("div");
    el.className = "toast" + (isError ? " error" : " success");
    el.textContent = message;
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    document.body.appendChild(el);
    toastTimer = setTimeout(function () { el.remove(); toastTimer = null; }, 2500);
  }

  /* ---- Confirm Dialog ---- */
  function confirmDialog(message) {
    return new Promise(function (resolve) {
      dom.confirmMessage.textContent = message;
      dom.confirmDialog.showModal();
      confirmResolve = resolve;
    });
  }

  function closeConfirmDialog(confirmed) {
    dom.confirmDialog.close();
    if (confirmResolve) { confirmResolve(confirmed); confirmResolve = null; }
  }

  /* ---- File Handling ---- */
  function setupDropZone() {
    dom.dropZone.addEventListener("click", function () { dom.fileInput.click(); });
    dom.dropZone.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); dom.fileInput.click(); } });
    dom.fileInput.addEventListener("change", function () {
      if (dom.fileInput.files && dom.fileInput.files[0]) {
        state.selectedFile = dom.fileInput.files[0];
        dom.dropZone.classList.add("file-selected");
        dom.dropText.textContent = state.selectedFile.name;
        dom.uploadError.textContent = "";
        updateUploadButton();
      }
    });
    dom.dropZone.addEventListener("dragover", function (e) { e.preventDefault(); dom.dropZone.classList.add("dragover"); });
    dom.dropZone.addEventListener("dragleave", function () { dom.dropZone.classList.remove("dragover"); });
    dom.dropZone.addEventListener("drop", function (e) {
      e.preventDefault();
      dom.dropZone.classList.remove("dragover");
      var files = e.dataTransfer.files;
      if (files && files[0]) {
        state.selectedFile = files[0];
        dom.fileInput.files = files;
        dom.dropZone.classList.add("file-selected");
        dom.dropText.textContent = state.selectedFile.name;
        dom.uploadError.textContent = "";
        updateUploadButton();
      }
    });
  }

  function updateUploadButton() {
    var hasProject = !!dom.projectName.value.trim();
    var hasFile = !!state.selectedFile;
    var modelReady = state.health && state.health.model_ready === true;
    dom.btnUpload.disabled = !(hasProject && hasFile && modelReady);
  }

  /* ---- Init ---- */
  function init() {
    cacheDom();
    setupDropZone();
    dom.projectName.addEventListener("input", updateUploadButton);
    dom.statusFilter.addEventListener("change", function () { fetchJobs(dom.statusFilter.value || undefined); });
    dom.btnUpload.addEventListener("click", handleUpload);
    dom.btnSaveReview.addEventListener("click", handleSaveReview);
    dom.btnDownloadJson.addEventListener("click", handleDownloadJson);
    dom.btnDownloadCsv.addEventListener("click", handleDownloadCsv);
    dom.btnDownloadZip.addEventListener("click", handleDownloadZip);
    dom.btnRetry.addEventListener("click", handleRetry);
    dom.btnCancel.addEventListener("click", function () { closeConfirmDialog(false); });
    dom.btnConfirm.addEventListener("click", function () { closeConfirmDialog(true); });
    window.addEventListener("beforeunload", cancelPolling);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && dom.confirmDialog.open) closeConfirmDialog(false); });
    updateUploadButton();
    updateRetryButton();
    fetchHealth().then(function () { return fetchStats(); }).then(function () { return fetchJobs(); }).then(function () { showEvidenceState("empty"); }).catch(function () { showEvidenceState("empty"); dom.evidenceEmpty.querySelector(".empty-desc").textContent = "无法连接服务，请确认服务已启动。"; });
  }

  if (document.readyState === "complete" || document.readyState === "interactive") { init(); }
  else { document.addEventListener("DOMContentLoaded", init); }
})();
