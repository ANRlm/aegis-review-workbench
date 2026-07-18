(function () {
  'use strict';

  const API_BASE = '/api';
  const POLL_MS = 1000;

  const $ = (s, p) => (p || document).querySelector(s);
  const $$ = (s, p) => [...(p || document).querySelectorAll(s)];

  /* DOM refs */
  const healthModel = $('#healthModel');
  const healthFfmpeg = $('#healthFfmpeg');
  const healthStorage = $('#healthStorage');
  const statTotal = $('#statTotal');
  const statPass = $('#statPass');
  const statReview = $('#statReview');
  const statReject = $('#statReject');
  const statFailed = $('#statFailed');

  const uploadForm = $('#uploadForm');
  const projectName = $('#projectName');
  const assetFile = $('#assetFile');
  const dropZone = $('#dropZone');
  const submitBtn = $('#submitBtn');
  const formMsg = $('#formMsg');

  const historyList = $('#historyList');
  const filterBtns = $$('.filter-btn');
  const confirmModal = $('#confirmModal');
  const modalConfirm = $('#modalConfirm');
  const modalCancel = $('#modalCancel');

  const evidenceContent = $('#evidenceContent');
  const defaultEmpty = $('#defaultEmpty');
  const loadingState = $('#loadingState');
  const loadingText = $('#loadingText');
  const failedState = $('#failedState');
  const failedText = $('#failedText');
  const failedError = $('#failedError');
  const completedState = $('#completedState');
  const assetPreview = $('#assetPreview');
  const assetLabel = $('#assetLabel');
  const autoDecisionBadge = $('#autoDecisionBadge');
  const autoDecisionText = $('#autoDecisionText');
  const detectionList = $('#detectionList');
  const evidenceList = $('#evidenceList');

  const reviewPlaceholder = $('#reviewPlaceholder');
  const reviewContent = $('#reviewContent');
  const reviewAutoDecision = $('#reviewAutoDecision');
  const reviewFinalDecision = $('#reviewFinalDecision');
  const saveReviewBtn = $('#saveReviewBtn');
  const reviewMsg = $('#reviewMsg');
  const reviewer = $('#reviewer');
  const note = $('#note');
  const downloadsArea = $('#downloadsArea');
  const downloadJson = $('#downloadJson');
  const downloadCsv = $('#downloadCsv');
  const downloadZip = $('#downloadZip');

  const toast = $('#toast');

  /* state */
  let jobs = [];
  let currentFilter = '';
  let selectedJobId = null;
  let pollTimer = null;
  let modelReady = true;
  let currentAssetUrl = null;

  function apiUrl(path) {
    return API_BASE + path;
  }

  function showToast(msg, type) {
    toast.textContent = msg;
    toast.className = 'toast show' + (type ? ' ' + type : '');
    clearTimeout(toast._hide);
    toast._hide = setTimeout(function () { toast.className = 'toast'; }, 3000);
  }

  function escapeHtml(s) {
    if (!s) return '';
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function formatDate(iso) {
    if (!iso) return '--';
    try { var d = new Date(iso); return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); }
    catch (e) { return iso; }
  }

  function statusLabel(st) {
    return { created: '已创建', queued: '排队中', running: '分析中', completed: '已完成', failed: '失败' }[st] || st;
  }

  function decisionLabel(d) {
    return { pass: '通过', review: '待复核', reject: '不通过' }[d] || '--';
  }

  async function apiFetch(path, opts) {
    var res = await fetch(apiUrl(path), opts);
    var ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) {
      return { ok: res.ok, status: res.status, body: await res.json() };
    }
    return { ok: res.ok, status: res.status, body: null, raw: res };
  }

  /* Health & stats */
  async function loadHealth() {
    try {
      var r = await apiFetch('/health');
      if (r.ok && r.body && r.body.ok) {
        modelReady = r.body.model_ready || false;
        setHealthBadge(healthModel, '模型', r.body.model_ready);
        setHealthBadge(healthFfmpeg, 'FFmpeg', r.body.ffmpeg_ready);
        setHealthBadge(healthStorage, '存储', r.body.storage_ready);
      }
    } catch (e) {}
  }

  function setHealthBadge(el, label, ready) {
    if (ready === true) { el.textContent = label + ' ✓'; el.className = 'health-item ok'; }
    else if (ready === false) { el.textContent = label + ' ✗'; el.className = 'health-item err'; }
    else { el.textContent = label + ' --'; el.className = 'health-item'; }
  }

  async function loadStats() {
    try {
      var r = await apiFetch('/stats');
      if (r.ok && r.body && r.body.ok) {
        var s = r.body.stats || {};
        statTotal.textContent = s.total ?? 0;
        statPass.textContent = s.pass ?? 0;
        statReview.textContent = s.review ?? 0;
        statReject.textContent = s.reject ?? 0;
        statFailed.textContent = s.failed ?? 0;
      }
    } catch (e) {}
  }

  /* Job list */
  async function loadJobs() {
    try {
      var q = currentFilter ? '?status=' + encodeURIComponent(currentFilter) : '';
      var r = await apiFetch('/jobs' + q);
      if (r.ok && r.body && r.body.ok) {
        jobs = r.body.jobs || [];
        renderHistory();
      }
    } catch (e) {}
  }

  function renderHistory() {
    if (jobs.length === 0) {
      historyList.innerHTML = '<div class="empty-state">暂无任务</div>';
      return;
    }
    historyList.innerHTML = jobs.map(function (j) {
      var active = j.job_id === selectedJobId ? ' active' : '';
      return '<div class="history-item' + active + '" data-job-id="' + j.job_id + '" role="listitem">' +
        '<div class="job-name" title="' + escapeHtml(j.asset_name || '') + '">' + escapeHtml(j.asset_name || '未知') + '</div>' +
        '<div class="job-meta"><span class="job-status ' + j.status + '">' + statusLabel(j.status) + '</span><span>' + formatDate(j.created_at) + '</span></div>' +
        '<div class="job-actions">' +
        '<button class="reopen-btn" data-job-id="' + j.job_id + '">打开</button>' +
        '<button class="delete-btn" data-job-id="' + j.job_id + '">删除</button>' +
        '</div></div>';
    }).join('');

    $$('.history-item', historyList).forEach(function (el) {
      el.addEventListener('click', function (e) {
        if (e.target.closest('.job-actions')) return;
        selectJob(this.dataset.jobId);
      });
    });
    $$('.reopen-btn', historyList).forEach(function (el) {
      el.addEventListener('click', function (e) { e.stopPropagation(); selectJob(this.dataset.jobId); });
    });
    $$('.delete-btn', historyList).forEach(function (el) {
      el.addEventListener('click', function (e) { e.stopPropagation(); showDeleteConfirm(this.dataset.jobId); });
    });
  }

  /* Job selection & polling */
  function selectJob(jobId) {
    stopPolling();
    selectedJobId = jobId;
    renderHistory();
    currentAssetUrl = null;
    fetchJobDetail(jobId);
  }

  async function fetchJobDetail(jobId) {
    try {
      var r = await apiFetch('/jobs/' + encodeURIComponent(jobId));
      if (!r.ok) {
        showEvidenceError('无法获取任务', '任务不存在或已被删除。');
        return;
      }
      var j = r.body.job || r.body;
      currentAssetUrl = j.asset_url || null;
      var status = j.status || 'unknown';

      if (status === 'completed' || status === 'failed') {
        stopPolling();
        if (status === 'completed') {
          fetchReport(jobId);
          loadStats();
        } else {
          showEvidenceError('任务失败', j.error || '未知错误');
        }
      } else {
        showEvidenceLoading(statusLabel(status) + '…');
        startPolling(jobId);
      }
      updateReviewPanel(j);
    } catch (err) {
      showEvidenceError('网络错误', '无法连接到服务器，请检查网络后重试。');
    }
  }

  function startPolling(jobId) {
    stopPolling();
    pollTimer = setInterval(function () { fetchJobDetail(jobId); }, POLL_MS);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  /* Evidence display */
  function showEvidenceEmpty() {
    hideAllEvidence();
    defaultEmpty.hidden = false;
    reviewPlaceholder.hidden = false;
    reviewContent.hidden = true;
  }

  function showEvidenceLoading(msg) {
    hideAllEvidence();
    loadingState.hidden = false;
    loadingText.textContent = msg || '任务处理中…';
  }

  function showEvidenceError(title, errMsg) {
    hideAllEvidence();
    failedState.hidden = false;
    failedText.textContent = title || '任务失败';
    failedError.textContent = errMsg || '';
  }

  function hideAllEvidence() {
    defaultEmpty.hidden = true;
    loadingState.hidden = true;
    failedState.hidden = true;
    completedState.hidden = true;
  }

  function fetchReport(jobId) {
    apiFetch('/jobs/' + encodeURIComponent(jobId) + '/report').then(function (r) {
      if (r.ok && r.body && r.body.ok) {
        displayReport(r.body.report, jobId);
      } else {
        showEvidenceError('加载失败', '无法加载分析报告。');
      }
    }).catch(function () {
      showEvidenceError('网络错误', '无法加载分析报告。');
    });
  }

  function displayReport(report, jobId) {
    hideAllEvidence();
    completedState.hidden = false;

    var detections = report.detections || [];
    var evidenceFrames = report.evidence_frames || [];
    var autoDecision = report.auto_decision || '--';
    var finalDecision = report.final_decision || autoDecision;

    autoDecisionText.textContent = decisionLabel(autoDecision);
    autoDecisionBadge.className = 'decision-badge ' + (autoDecision || '');
    reviewAutoDecision.textContent = decisionLabel(autoDecision);
    reviewFinalDecision.textContent = decisionLabel(finalDecision);

    if (currentAssetUrl) {
      var isVideo = currentAssetUrl.match(/\.(mp4|mov)$/i);
      assetPreview.innerHTML = '';
      if (isVideo) {
        var v = document.createElement('video');
        v.src = currentAssetUrl;
        v.controls = true;
        v.preload = 'metadata';
        assetPreview.appendChild(v);
      } else {
        var img = document.createElement('img');
        img.src = currentAssetUrl;
        img.alt = '素材预览';
        img.loading = 'lazy';
        assetPreview.appendChild(img);
      }
    } else {
      assetPreview.innerHTML = '<p class="asset-label">素材地址不可用</p>';
    }
    assetLabel.textContent = jobId || '';

    renderDetections(detections);
    renderEvidenceFrames(evidenceFrames, jobId);

    if (report.downloads) {
      downloadsArea.hidden = false;
      downloadJson.href = '/api/jobs/' + encodeURIComponent(jobId) + '/report';
      downloadJson.hidden = false;
      if (report.downloads.csv) {
        downloadCsv.href = report.downloads.csv;
        downloadCsv.hidden = false;
      } else { downloadCsv.hidden = true; }
      if (report.downloads.zip) {
        downloadZip.href = report.downloads.zip;
        downloadZip.hidden = false;
      } else { downloadZip.hidden = true; }
    } else {
      downloadsArea.hidden = true;
    }

    updateReviewContent(report, jobId);
  }

  function renderDetections(detections) {
    if (detections.length === 0) {
      detectionList.innerHTML = '<p style="font-size:13px;color:var(--muted);">未检测到目标</p>';
      return;
    }
    var rows = detections.map(function (d) {
      return '<tr><td>' + escapeHtml(d.class_name || '--') + '</td>' +
        '<td>' + (d.confidence != null ? (d.confidence * 100).toFixed(0) + '%' : '--') + '</td>' +
        '<td>' + (d.frame_index != null ? '#' + d.frame_index : '--') + '</td>' +
        '<td>' + (d.timestamp_seconds != null ? d.timestamp_seconds.toFixed(1) + 's' : '--') + '</td></tr>';
    }).join('');
    detectionList.innerHTML = '<table class="detection-table">' +
      '<thead><tr><th>类别</th><th>置信度</th><th>帧</th><th>时间</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function renderEvidenceFrames(frames, jobId) {
    if (frames.length === 0) {
      evidenceList.innerHTML = '<p style="font-size:13px;color:var(--muted);">无证据帧</p>';
      return;
    }
    var base = '/api/jobs/' + encodeURIComponent(jobId) + '/artifacts/';
    evidenceList.innerHTML = frames.map(function (f) {
      var src = f.indexOf('http') === 0 ? f : base + encodeURIComponent(f);
      var label = f.replace(/^frame_0*/, '帧 ').replace(/\.\w+$/, '');
      return '<div class="evidence-item"><img src="' + src + '" alt="证据帧" loading="lazy"><div class="evidence-meta">' + escapeHtml(label) + '</div></div>';
    }).join('');
  }

  /* Review panel */
  function updateReviewPanel(job) {
    if (!job || job.status === 'created' || job.status === 'queued' || job.status === 'running' || job.status === 'failed') {
      reviewPlaceholder.hidden = false;
      reviewContent.hidden = true;
      return;
    }
    if (job.status === 'completed') {
      return;
    }
    reviewPlaceholder.hidden = false;
    reviewContent.hidden = true;
  }

  function updateReviewContent(report, jobId) {
    reviewPlaceholder.hidden = true;
    reviewContent.hidden = false;
    reviewAutoDecision.textContent = decisionLabel(report.auto_decision);
    reviewFinalDecision.textContent = decisionLabel(report.final_decision || report.auto_decision);
    reviewer.value = report.reviewer || '';
    note.value = report.note || '';
    reviewMsg.textContent = '';
    reviewMsg.className = 'form-msg';

    var current = report.final_decision || report.auto_decision;
    $$('input[name="decision"]').forEach(function (r) { r.checked = r.value === current; });

    saveReviewBtn._jobId = jobId;
    saveReviewBtn._report = report;
  }

  saveReviewBtn.addEventListener('click', async function () {
    var jobId = this._jobId;
    if (!jobId) return;

    var decisionEl = $('input[name="decision"]:checked');
    var decision = decisionEl ? decisionEl.value : null;
    var reviewerName = reviewer.value.trim();
    var noteText = note.value.trim();

    if (!decision) {
      reviewMsg.textContent = '请选择审核结论。';
      reviewMsg.className = 'form-msg error';
      return;
    }
    if (!reviewerName) {
      reviewMsg.textContent = '请填写负责人姓名。';
      reviewMsg.className = 'form-msg error';
      return;
    }

    try {
      var r = await apiFetch('/jobs/' + encodeURIComponent(jobId) + '/review', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision: decision, reviewer: reviewerName, note: noteText }),
      });
      if (r.ok && r.body && r.body.ok) {
        reviewMsg.textContent = '改判已保存。';
        reviewMsg.className = 'form-msg success';
        showToast('审核结论已保存', 'success');
        if (r.body.report) {
          updateReviewContent(r.body.report, jobId);
        }
        loadStats();
      } else {
        var msg = (r.body && r.body.error && r.body.error.message) || '保存失败';
        reviewMsg.textContent = msg;
        reviewMsg.className = 'form-msg error';
      }
    } catch (err) {
      reviewMsg.textContent = '网络错误，请重试。';
      reviewMsg.className = 'form-msg error';
    }
  });

  /* Upload */
  uploadForm.addEventListener('submit', async function (e) {
    e.preventDefault();
    var name = projectName.value.trim();
    var file = assetFile.files[0];

    var droppedFile = dropZone._droppedFile;
    var uploadFile = file || droppedFile;

    if (!name) {
      formMsg.textContent = '请输入项目名称。';
      formMsg.className = 'form-msg error';
      return;
    }
    if (!uploadFile) {
      formMsg.textContent = '请选择或拖放素材文件。';
      formMsg.className = 'form-msg error';
      return;
    }
    if (!modelReady) {
      formMsg.textContent = '模型尚未就绪，无法进行分析。';
      formMsg.className = 'form-msg error';
      return;
    }
    if (uploadFile.size > 200 * 1024 * 1024) {
      formMsg.textContent = '文件大小不能超过 200MB。';
      formMsg.className = 'form-msg error';
      return;
    }

    var settings = buildSettings();
    if (!settings) return;

    submitBtn.disabled = true;
    formMsg.textContent = '正在上传…';
    formMsg.className = 'form-msg';

    try {
      var fd = new FormData();
      fd.append('asset', uploadFile);
      fd.append('project_name', name);
      fd.append('settings', JSON.stringify(settings));

      var r = await apiFetch('/jobs', { method: 'POST', body: fd });
      if (r.ok && r.body && r.body.ok) {
        var job = r.body.job;
        formMsg.textContent = '任务已创建，开始分析…';
        formMsg.className = 'form-msg success';
        uploadForm.reset();
        dropZone._droppedFile = null;
        dropZone.querySelector('.drop-hint').textContent = '或将文件拖放到此处';
        await triggerAnalyze(job.job_id);
        await loadJobs();
        await loadStats();
      } else {
        var msg = (r.body && r.body.error && r.body.error.message) || '上传失败';
        formMsg.textContent = msg;
        formMsg.className = 'form-msg error';
        submitBtn.disabled = false;
      }
    } catch (err) {
      formMsg.textContent = '网络错误，请重试。';
      formMsg.className = 'form-msg error';
      submitBtn.disabled = false;
    }
  });

  function buildSettings() {
    try {
      return {
        risk_classes: ($('#riskClasses').value || 'enemy').split(',').map(function (s) { return s.trim(); }).filter(Boolean),
        reject_confidence: parseFloat($('#rejectConf').value) || 0.60,
        review_confidence: parseFloat($('#reviewConf').value) || 0.35,
        inference_confidence: parseFloat($('#inferConf').value) || 0.25,
        min_evidence_frames: parseInt($('#minEvidence').value, 10) || 1,
        sample_interval_seconds: 1.0,
        max_sample_frames: 120,
      };
    } catch (e) {
      formMsg.textContent = '规则配置无效。';
      formMsg.className = 'form-msg error';
      return null;
    }
  }

  async function triggerAnalyze(jobId) {
    try {
      var r = await apiFetch('/jobs/' + encodeURIComponent(jobId) + '/analyze', { method: 'POST' });
      if (r.ok) {
        selectJob(jobId);
      } else {
        var msg = (r.body && r.body.error && r.body.error.message) || '分析启动失败';
        showToast(msg, 'error');
      }
    } catch (err) {
      showToast('网络错误，分析启动失败。', 'error');
    } finally {
      submitBtn.disabled = false;
    }
  }

  /* Drag & drop */
  dropZone.addEventListener('click', function () { assetFile.click(); });
  dropZone.addEventListener('dragover', function (e) { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', function () { dropZone.classList.remove('drag-over'); });
  dropZone.addEventListener('drop', function (e) {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length > 0) {
      dropZone._droppedFile = e.dataTransfer.files[0];
      dropZone.querySelector('.drop-hint').textContent = dropZone._droppedFile.name;
    }
  });
  assetFile.addEventListener('change', function () {
    dropZone._droppedFile = null;
    dropZone.querySelector('.drop-hint').textContent = this.files.length > 0 ? this.files[0].name : '或将文件拖放到此处';
  });

  /* Filter */
  filterBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      filterBtns.forEach(function (b) { b.classList.remove('active'); });
      this.classList.add('active');
      currentFilter = this.dataset.filter || '';
      loadJobs();
    });
  });

  /* Delete confirm */
  var deleteTargetId = null;
  function showDeleteConfirm(jobId) {
    deleteTargetId = jobId;
    confirmModal.hidden = false;
    modalConfirm.focus();
  }
  modalCancel.addEventListener('click', function () { confirmModal.hidden = true; deleteTargetId = null; });
  modalConfirm.addEventListener('click', async function () {
    if (!deleteTargetId) return;
    confirmModal.hidden = true;
    try {
      var r = await apiFetch('/jobs/' + encodeURIComponent(deleteTargetId), { method: 'DELETE' });
      if (r.ok) {
        showToast('任务已删除', 'success');
        if (selectedJobId === deleteTargetId) {
          stopPolling();
          selectedJobId = null;
          showEvidenceEmpty();
        }
        deleteTargetId = null;
        await loadJobs();
        await loadStats();
      } else {
        var msg = (r.body && r.body.error && r.body.error.message) || '删除失败';
        showToast(msg, 'error');
      }
    } catch (e) {
      showToast('网络错误，删除失败。', 'error');
    }
  });
  confirmModal.addEventListener('click', function (e) {
    if (e.target === this) { this.hidden = true; deleteTargetId = null; }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !confirmModal.hidden) {
      confirmModal.hidden = true; deleteTargetId = null;
    }
  });

  /* Unload */
  window.addEventListener('beforeunload', function () { stopPolling(); });

  /* Init */
  async function init() {
    await loadHealth();
    await loadStats();
    await loadJobs();
    showEvidenceEmpty();
  }
  init();
})();
