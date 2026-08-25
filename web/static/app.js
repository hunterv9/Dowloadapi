/**
 * Clipdesk — TikTok & Douyin Downloader
 * Universal Client Engine (WebSocket + REST Fallback)
 * SaaS Premium Edition
 */

// ── Application State ──
const State = {
  currentView: "view-single",
  activeVideoInfo: null,
  activeSingleTaskId: null,
  activeBatchTaskId: null,
  downloadsList: [],
  config: {},
  ws: null,
  wsConnected: false,
  wsCallbacks: new Map(),
  reqIdCounter: 1
};

// ── DOM References ──
const Elements = {
  // Navigation & Titlebar
  navItems: document.querySelectorAll(".nav-item"),
  viewPanes: document.querySelectorAll(".view-pane"),
  sidebarDownloadsCount: document.getElementById("sidebar-downloads-count"),
  winMinBtn: document.getElementById("win-min-btn"),
  winMaxBtn: document.getElementById("win-max-btn"),
  winCloseBtn: document.getElementById("win-close-btn"),

  // View 1: Single Download
  singleUrlInput: document.getElementById("single-url-input"),
  btnPasteClipboard: document.getElementById("btn-paste-clipboard"),
  btnAnalyzeVideo: document.getElementById("btn-analyze-video"),
  videoPreviewBox: document.getElementById("video-preview-box"),
  previewThumbImg: document.getElementById("preview-thumb-img"),
  btnPreviewInApp: document.getElementById("btn-preview-in-app"),
  previewDurationTag: document.getElementById("preview-duration-tag"),
  previewPlatformBadge: document.getElementById("preview-platform-badge"),
  previewTitleText: document.getElementById("preview-title-text"),
  previewAuthorName: document.getElementById("preview-author-name"),
  previewAuthorHandle: document.getElementById("preview-author-handle"),
  btnStartDownloadVideo: document.getElementById("btn-start-download-video"),
  btnDownloadAudioOnly: document.getElementById("btn-download-audio-only"),
  singleProgressCard: document.getElementById("single-progress-card"),
  singleProgressFilename: document.getElementById("single-progress-filename"),
  singleProgressPercent: document.getElementById("single-progress-percent"),
  singleProgressBar: document.getElementById("single-progress-bar"),
  singleProgressSubtext: document.getElementById("single-progress-subtext"),

  // View 2: Batch / Profile
  profileInput: document.getElementById("profile-input"),
  btnStartProfileDownload: document.getElementById("btn-start-profile-download"),
  bulkUrlsTextarea: document.getElementById("bulk-urls-textarea"),
  btnStartBulkDownload: document.getElementById("btn-start-bulk-download"),
  batchProgressCard: document.getElementById("batch-progress-card"),
  batchProgressStatusText: document.getElementById("batch-progress-status-text"),
  batchProgressPercent: document.getElementById("batch-progress-percent"),
  batchProgressBar: document.getElementById("batch-progress-bar"),
  batchProgressSubtext: document.getElementById("batch-progress-subtext"),

  // View 3: Downloads Manager
  btnOpenDownloadFolder: document.getElementById("btn-open-download-folder"),
  btnRefreshDownloads: document.getElementById("btn-refresh-downloads"),
  downloadsSearchInput: document.getElementById("downloads-search-input"),
  downloadsStatCount: document.getElementById("downloads-stat-count"),
  downloadsStatSize: document.getElementById("downloads-stat-size"),
  downloadsGrid: document.getElementById("downloads-grid"),
  downloadsEmpty: document.getElementById("downloads-empty"),

  // View 4: Settings
  settingDownloadDir: document.getElementById("setting-download-dir"),
  settingVideoQuality: document.getElementById("setting-video-quality"),
  settingSaveMetadata: document.getElementById("setting-save-metadata"),
  settingCustomCookie: document.getElementById("setting-custom-cookie"),
  btnSaveSettings: document.getElementById("btn-save-settings"),

  // Video Player Modal
  videoPlayerModal: document.getElementById("video-player-modal"),
  modalVideoTitle: document.getElementById("modal-video-title"),
  modalVideoElement: document.getElementById("modal-video-element"),
  btnCloseModal: document.getElementById("btn-close-modal"),

  // Toast Container
  toastContainer: document.getElementById("toast-container")
};

// ==========================================================================
// SVG ICON HELPERS
// ==========================================================================
const Icons = {
  check: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  x: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  info: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
  warning: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
  download: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`,
  spinner: `<span class="spinner"></span>`,
};

// ==========================================================================
// TOAST NOTIFICATIONS — Premium
// ==========================================================================
function showToast(message, type = "info", duration = 3500) {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  const iconMap = {
    success: Icons.check,
    error: Icons.x,
    info: Icons.info,
    warning: Icons.warning
  };

  toast.innerHTML = `
    <span class="toast-icon">${iconMap[type] || iconMap.info}</span>
    <span style="flex:1; min-width:0;">${message}</span>
  `;

  // Set progress bar duration
  toast.style.setProperty('--toast-duration', `${duration}ms`);

  Elements.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(40px) scale(0.95)";
    toast.style.transition = "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ==========================================================================
// UNIFIED ENGINE CLIENT (WEBSOCKET + REST FALLBACK)
// ==========================================================================
function initEngineConnection() {
  const WS_URL = "ws://127.0.0.1:8765";

  try {
    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      State.ws = ws;
      State.wsConnected = true;
      showToast("Đã kết nối Engine WebSocket", "success");
      loadInitialData();
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleServerMessage(msg);
      } catch (e) {
        console.error("WS Parse error:", e);
      }
    };

    ws.onerror = () => {
      fallbackToRestMode();
    };

    ws.onclose = () => {
      if (State.wsConnected) {
        showToast("Mất kết nối WebSocket, chuyển REST", "warning");
      }
      fallbackToRestMode();
    };
  } catch (e) {
    fallbackToRestMode();
  }
}

function fallbackToRestMode() {
  State.wsConnected = false;
  State.ws = null;
  loadInitialData();
}

function sendAction(action, payload = {}) {
  return new Promise((resolve, reject) => {
    if (State.wsConnected && State.ws && State.ws.readyState === WebSocket.OPEN) {
      const id = State.reqIdCounter++;
      State.wsCallbacks.set(id, { resolve, reject });
      State.ws.send(JSON.stringify({ id, action, payload }));
    } else {
      // Fallback REST API mappings
      handleRestAction(action, payload).then(resolve).catch(reject);
    }
  });
}

function handleServerMessage(msg) {
  // Check if response to a request
  if (msg.id && State.wsCallbacks.has(msg.id)) {
    const { resolve, reject } = State.wsCallbacks.get(msg.id);
    State.wsCallbacks.delete(msg.id);
    if (msg.status === "error") {
      reject(new Error(msg.error));
    } else {
      resolve(msg.data);
    }
    return;
  }

  // Handle push broadcast events
  if (msg.event === "DOWNLOAD_PROGRESS") {
    const pct = msg.percent || 0;
    Elements.singleProgressPercent.textContent = `${pct}%`;
    Elements.singleProgressBar.style.width = `${pct}%`;
    let sizeInfo = "";
    if (msg.downloaded && msg.total) {
      const mbDown = (msg.downloaded / (1024 * 1024)).toFixed(1);
      const mbTotal = (msg.total / (1024 * 1024)).toFixed(1);
      sizeInfo = ` • ${mbDown} MB / ${mbTotal} MB`;
    }
    Elements.singleProgressSubtext.textContent = `Đang tải dữ liệu...${sizeInfo}`;
  } else if (msg.event === "DOWNLOAD_COMPLETED") {
    Elements.singleProgressPercent.textContent = "100%";
    Elements.singleProgressBar.style.width = "100%";
    Elements.singleProgressSubtext.textContent = `Đã lưu: ${msg.result?.filename || "Video"}`;
    resetDownloadButton();
    showToast("Tải video thành công!", "success");
    loadDownloads();
  } else if (msg.event === "DOWNLOAD_FAILED") {
    Elements.singleProgressSubtext.textContent = `Lỗi: ${msg.error}`;
    resetDownloadButton();
    showToast(`Tải thất bại: ${msg.error}`, "error");
  } else if (msg.event === "BATCH_PROGRESS") {
    const pct = msg.total > 0 ? Math.round((msg.index / msg.total) * 100) : 0;
    Elements.batchProgressPercent.textContent = `${pct}%`;
    Elements.batchProgressBar.style.width = `${pct}%`;
    Elements.batchProgressStatusText.textContent = msg.message || "Đang xử lý...";
    Elements.batchProgressSubtext.textContent = `Tiến độ: ${msg.index || 0} / ${msg.total || 0} video`;
  } else if (msg.event === "BATCH_COMPLETED") {
    Elements.batchProgressPercent.textContent = "100%";
    Elements.batchProgressBar.style.width = "100%";
    Elements.batchProgressStatusText.textContent = "Hoàn tất!";
    Elements.batchProgressSubtext.textContent = `Đã lưu ${msg.result?.downloaded || 0} video.`;
    showToast("Tải hàng loạt thành công!", "success");
    loadDownloads();
  } else if (msg.event === "BATCH_FAILED") {
    Elements.batchProgressStatusText.textContent = `Lỗi: ${msg.error}`;
    Elements.batchProgressSubtext.textContent = msg.error || "Không tải được video.";
    showToast(`Lỗi: ${msg.error}`, "error");
  }
}

function resetDownloadButton() {
  Elements.btnStartDownloadVideo.disabled = false;
  Elements.btnStartDownloadVideo.innerHTML = `${Icons.download}<span>Tải Video Full HD</span>`;
}

async function handleRestAction(action, payload) {
  if (action === "GET_CONFIG") {
    const res = await fetch("/api/config");
    const data = await res.json();
    return data;
  } else if (action === "SAVE_CONFIG") {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return (await res.json()).config;
  } else if (action === "ANALYZE_VIDEO") {
    const res = await fetch("/api/video-info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: payload.url })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Lỗi phân tích video");
    return data.data;
  } else if (action === "DOWNLOAD_SINGLE") {
    const res = await fetch("/api/download-single", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: payload.url })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Lỗi khởi động tải");
    pollRestTask(data.task_id);
    return data;
  } else if (action === "DOWNLOAD_PROFILE") {
    const res = await fetch("/api/download-profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Lỗi tải hàng loạt");
    pollRestBatchTask(data.task_id);
    return data;
  } else if (action === "GET_DOWNLOADS") {
    const res = await fetch("/api/downloads");
    return await res.json();
  } else if (action === "OPEN_FOLDER") {
    const res = await fetch("/api/open-folder", { method: "POST" });
    return await res.json();
  } else if (action === "OPEN_FILE") {
    const res = await fetch("/api/open-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: payload.path })
    });
    return await res.json();
  } else if (action === "DELETE_DOWNLOAD") {
    const res = await fetch("/api/delete-download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: payload.path })
    });
    return await res.json();
  }
}

function pollRestTask(taskId) {
  const timer = setInterval(async () => {
    try {
      const res = await fetch(`/api/task-status/${taskId}`);
      if (!res.ok) { clearInterval(timer); return; }
      const data = await res.json();
      if (data.status === "downloading") {
        Elements.singleProgressPercent.textContent = `${data.progress || 0}%`;
        Elements.singleProgressBar.style.width = `${data.progress || 0}%`;
      } else if (data.status === "completed") {
        clearInterval(timer);
        Elements.singleProgressPercent.textContent = "100%";
        Elements.singleProgressBar.style.width = "100%";
        Elements.singleProgressSubtext.textContent = `Đã lưu: ${data.filename || "Video"}`;
        resetDownloadButton();
        showToast("Tải video thành công!", "success");
        loadDownloads();
      } else if (data.status === "failed") {
        clearInterval(timer);
        showToast(`Tải thất bại: ${data.error}`, "error");
        resetDownloadButton();
      }
    } catch (e) {
      clearInterval(timer);
    }
  }, 500);
}

function pollRestBatchTask(taskId) {
  const timer = setInterval(async () => {
    try {
      const res = await fetch(`/api/task-status/${taskId}`);
      if (!res.ok) { clearInterval(timer); return; }
      const data = await res.json();
      if (data.status === "resolving") {
        Elements.batchProgressStatusText.textContent = data.message || "Đang quét kênh...";
        Elements.batchProgressSubtext.textContent = "Đang tìm video trong profile...";
      } else if (data.status === "downloading") {
        Elements.batchProgressPercent.textContent = `${data.progress || 0}%`;
        Elements.batchProgressBar.style.width = `${data.progress || 0}%`;
        Elements.batchProgressStatusText.textContent = data.message || "Đang xử lý...";
      } else if (data.status === "completed") {
        clearInterval(timer);
        Elements.batchProgressPercent.textContent = "100%";
        Elements.batchProgressBar.style.width = "100%";
        Elements.batchProgressStatusText.textContent = data.message || "Hoàn tất!";
        showToast("Tải hàng loạt thành công!", "success");
        loadDownloads();
      } else if (data.status === "failed") {
        clearInterval(timer);
        Elements.batchProgressStatusText.textContent = "Không thể tải theo kênh";
        Elements.batchProgressSubtext.textContent = data.error || data.message || "Không tìm thấy video trong profile.";
        showToast(`Tải thất bại: ${data.error}`, "error");
      }
    } catch (e) {
      clearInterval(timer);
    }
  }, 800);
}

// ==========================================================================
// VIEW 1: SINGLE DOWNLOAD LOGIC
// ==========================================================================
function initSingleView() {
  Elements.btnPasteClipboard.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text && (text.includes("tiktok.com") || text.includes("douyin.com"))) {
        Elements.singleUrlInput.value = text.trim();
        showToast("Đã dán liên kết từ clipboard", "success");
        analyzeSingleVideo(text.trim());
      } else if (text) {
        Elements.singleUrlInput.value = text.trim();
        showToast("Đã dán văn bản", "info");
      } else {
        showToast("Clipboard đang trống", "warning");
      }
    } catch (e) {
      showToast("Không thể đọc clipboard", "warning");
    }
  });

  Elements.singleUrlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      analyzeSingleVideo(Elements.singleUrlInput.value.trim());
    }
  });

  Elements.btnAnalyzeVideo.addEventListener("click", () => {
    analyzeSingleVideo(Elements.singleUrlInput.value.trim());
  });

  Elements.btnPreviewInApp.addEventListener("click", () => {
    if (State.activeVideoInfo && State.activeVideoInfo.download_url) {
      openVideoModal(State.activeVideoInfo.title || "Xem trước Video", State.activeVideoInfo.download_url);
    }
  });

  Elements.btnStartDownloadVideo.addEventListener("click", () => {
    if (!State.activeVideoInfo) return;
    startSingleDownload(State.activeVideoInfo.url || Elements.singleUrlInput.value.trim());
  });

  Elements.btnDownloadAudioOnly.addEventListener("click", () => {
    if (State.activeVideoInfo && State.activeVideoInfo.download_url) {
      window.open(State.activeVideoInfo.download_url, "_blank");
      showToast("Đang mở luồng tải âm thanh", "info");
    }
  });
}

async function analyzeSingleVideo(url) {
  if (!url) {
    showToast("Vui lòng dán liên kết TikTok hoặc Douyin", "warning");
    Elements.singleUrlInput.focus();
    return;
  }

  Elements.btnAnalyzeVideo.disabled = true;
  Elements.btnAnalyzeVideo.innerHTML = `${Icons.spinner}<span>Đang phân tích...</span>`;
  Elements.videoPreviewBox.classList.remove("active");

  try {
    const info = await sendAction("ANALYZE_VIDEO", { url });
    State.activeVideoInfo = info;
    renderSinglePreview(info);
    showToast("Phân tích thành công!", "success");
  } catch (err) {
    showToast(err.message || "Lỗi khi lấy thông tin video", "error");
  } finally {
    Elements.btnAnalyzeVideo.disabled = false;
    Elements.btnAnalyzeVideo.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg><span>Phân Tích</span>`;
  }
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

function renderSinglePreview(info) {
  Elements.previewThumbImg.src = info.thumbnail || "";
  Elements.previewTitleText.textContent = info.title || "Video không có tiêu đề";
  Elements.previewAuthorName.textContent = info.nickname || info.uploader || "Creator";
  Elements.previewAuthorHandle.textContent = `@${info.uploader || 'user'}`;
  Elements.previewDurationTag.textContent = formatDuration(info.duration);

  const isDouyin = (info.url && info.url.includes("douyin.com")) || (info.id && String(info.id).length < 18);
  Elements.previewPlatformBadge.className = `preview-platform-badge ${isDouyin ? 'douyin' : 'tiktok'}`;
  Elements.previewPlatformBadge.textContent = isDouyin ? 'Douyin (抖音)' : 'TikTok';

  Elements.videoPreviewBox.classList.add("active");
}

async function startSingleDownload(url) {
  Elements.btnStartDownloadVideo.disabled = true;
  Elements.btnStartDownloadVideo.innerHTML = `${Icons.spinner}<span>Đang gửi yêu cầu...</span>`;

  Elements.singleProgressCard.classList.add("active");
  Elements.singleProgressPercent.textContent = "0%";
  Elements.singleProgressBar.style.width = "0%";
  Elements.singleProgressSubtext.textContent = "Đang kết nối máy chủ CDN...";

  try {
    await sendAction("DOWNLOAD_SINGLE", { url });
  } catch (err) {
    showToast(err.message, "error");
    resetDownloadButton();
  }
}

// ==========================================================================
// VIEW 2: BATCH & PROFILE DOWNLOAD
// ==========================================================================
function initBatchView() {
  Elements.btnStartProfileDownload.addEventListener("click", async () => {
    const profile = Elements.profileInput.value.trim();
    if (!profile) {
      showToast("Vui lòng nhập @username hoặc link profile", "warning");
      return;
    }
    startBatchTask({ profile });
  });

  Elements.btnStartBulkDownload.addEventListener("click", async () => {
    const text = Elements.bulkUrlsTextarea.value.trim();
    if (!text) {
      showToast("Vui lòng dán ít nhất 1 đường link", "warning");
      return;
    }

    const urls = text.split("\n").map(u => u.trim()).filter(u => u.length > 0);
    if (urls.length === 0) {
      showToast("Không tìm thấy link hợp lệ", "warning");
      return;
    }

    startBatchTask({ profile: "bulk_list", urls });
  });
}

async function startBatchTask(payload) {
  Elements.batchProgressCard.classList.add("active");
  Elements.batchProgressPercent.textContent = "0%";
  Elements.batchProgressBar.style.width = "0%";
  Elements.batchProgressStatusText.textContent = "Đang khởi tạo...";
  Elements.batchProgressSubtext.textContent = "Đang gửi yêu cầu...";

  try {
    await sendAction("DOWNLOAD_PROFILE", payload);
    showToast("Đã bắt đầu tải hàng loạt!", "info");
  } catch (err) {
    Elements.batchProgressStatusText.textContent = "Không thể bắt đầu";
    Elements.batchProgressSubtext.textContent = err.message || "Kiểm tra lại profile.";
    showToast(err.message, "error");
  }
}

// ==========================================================================
// VIEW 3: DOWNLOADS MANAGER
// ==========================================================================
function initDownloadsView() {
  Elements.btnRefreshDownloads.addEventListener("click", () => {
    loadDownloads();
    showToast("Đã làm mới thư viện", "info");
  });

  Elements.btnOpenDownloadFolder.addEventListener("click", async () => {
    try {
      const result = await sendAction("OPEN_FOLDER");
      if (result && result.success === false) {
        throw new Error(result.error || "Không thể mở thư mục");
      }
      showToast("Đã mở thư mục", "success");
    } catch (e) {
      showToast(e.message || "Lỗi khi mở thư mục", "error");
    }
  });

  Elements.downloadsSearchInput.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase().trim();
    renderDownloadsGrid(q);
  });
}

async function loadDownloads() {
  try {
    const data = await sendAction("GET_DOWNLOADS");
    State.downloadsList = data.files || [];
    Elements.sidebarDownloadsCount.textContent = State.downloadsList.length;
    Elements.downloadsStatCount.textContent = State.downloadsList.length;
    Elements.downloadsStatSize.textContent = `${data.total_size_mb || 0} MB`;

    renderDownloadsGrid(Elements.downloadsSearchInput.value.toLowerCase().trim());
  } catch (e) {
    console.error(e);
  }
}

function renderDownloadsGrid(filterQuery = "") {
  Elements.downloadsGrid.innerHTML = "";

  const filtered = State.downloadsList.filter(item => {
    if (!filterQuery) return true;
    const nameMatch = (item.name || "").toLowerCase().includes(filterQuery);
    const titleMatch = (item.title || "").toLowerCase().includes(filterQuery);
    const authorMatch = (item.author || "").toLowerCase().includes(filterQuery);
    return nameMatch || titleMatch || authorMatch;
  });

  if (filtered.length === 0) {
    Elements.downloadsEmpty.style.display = "block";
    return;
  }

  Elements.downloadsEmpty.style.display = "none";

  filtered.forEach((item, index) => {
    const card = document.createElement("div");
    card.className = "media-item-card";
    card.style.animationDelay = `${index * 40}ms`;
    card.style.animation = `fadeInUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) ${index * 40}ms both`;

    const thumbSrc = item.thumbnail || "";
    const isDouyin = item.platform === "Douyin";

    card.innerHTML = `
      <div class="media-card-thumb">
        ${thumbSrc
          ? `<img src="${thumbSrc}" alt="thumb" loading="lazy">`
          : `<div style="display:flex;align-items:center;justify-content:center;height:100%;"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--text-tertiary);"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg></div>`
        }
        <span class="media-card-badge" style="background:${isDouyin ? 'rgba(6,182,212,0.85)' : 'rgba(236,72,153,0.85)'};">
          ${item.platform}
        </span>
      </div>

      <div class="media-card-content">
        <h4 class="media-card-title" title="${item.title || item.name}">${item.title || item.name}</h4>

        <div class="media-card-meta">
          <span>@${item.author || 'Creator'}</span>
          <span>${item.size_mb} MB</span>
        </div>

        <div class="media-card-actions">
          <button class="btn-card-action btn-play-inapp" title="Phát">
            ▶ Phát
          </button>
          <button class="btn-card-action btn-reveal-file" title="Vị trí">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            Vị trí
          </button>
          <button class="btn-card-action btn-delete" title="Xóa">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        </div>
      </div>
    `;

    card.querySelector(".btn-play-inapp").addEventListener("click", () => {
      const videoSrc = getPlayableVideoSource(item);
      if (!videoSrc) {
        showToast("Không tìm thấy đường dẫn phát video", "error");
        return;
      }
      openVideoModal(item.title || item.name, videoSrc);
    });

    card.querySelector(".btn-reveal-file").addEventListener("click", async () => {
      try {
        const result = await sendAction("OPEN_FILE", { path: item.path });
        if (result && result.success === false) {
          throw new Error(result.error || "Không thể mở vị trí file");
        }
        showToast("Đã mở vị trí file", "success");
      } catch (e) {
        showToast(e.message || "Lỗi mở vị trí file", "error");
      }
    });

    card.querySelector(".btn-delete").addEventListener("click", async () => {
      if (confirm(`Xóa video:\n"${item.title || item.name}"?`)) {
        try {
          await sendAction("DELETE_DOWNLOAD", { path: item.path });
          showToast("Đã xóa video", "success");
          loadDownloads();
        } catch (e) {
          showToast("Lỗi khi xóa file", "error");
        }
      }
    });

    Elements.downloadsGrid.appendChild(card);
  });
}

function getPlayableVideoSource(item) {
  if (item.stream_url) return item.stream_url;

  const filePath = String(item.path || "").replace(/\\/g, "/");
  if (/^[A-Za-z]:\//.test(filePath)) {
    return encodeURI(`file:///${filePath}`);
  }
  if (filePath.startsWith("/")) {
    return encodeURI(`file://${filePath}`);
  }
  return "";
}

// ==========================================================================
// VIEW 4: SETTINGS
// ==========================================================================
function initSettingsView() {
  Elements.btnSaveSettings.addEventListener("click", async () => {
    const payload = {
      download_dir: Elements.settingDownloadDir.value.trim(),
      video_quality: Elements.settingVideoQuality.value,
      save_metadata: Elements.settingSaveMetadata.checked,
      custom_cookie_string: Elements.settingCustomCookie.value.trim()
    };

    try {
      const cfg = await sendAction("SAVE_CONFIG", payload);
      State.config = cfg || payload;
      showToast("Đã lưu cấu hình!", "success");
    } catch (e) {
      showToast("Lỗi khi lưu cấu hình", "error");
    }
  });
}

async function loadInitialData() {
  try {
    const data = await sendAction("GET_CONFIG");
    State.config = data.config || {};
    const cfg = State.config;

    if (cfg.download_dir) Elements.settingDownloadDir.value = cfg.download_dir;
    if (cfg.video_quality) Elements.settingVideoQuality.value = cfg.video_quality;
    if (typeof cfg.save_metadata === "boolean") Elements.settingSaveMetadata.checked = cfg.save_metadata;
    if (cfg.custom_cookie_string) Elements.settingCustomCookie.value = cfg.custom_cookie_string;

    loadDownloads();
  } catch (e) {
    console.error(e);
  }
}

// ==========================================================================
// IN-APP VIDEO PLAYER MODAL
// ==========================================================================
function initVideoModal() {
  Elements.btnCloseModal.addEventListener("click", closeVideoModal);
  Elements.videoPlayerModal.addEventListener("click", (e) => {
    if (e.target === Elements.videoPlayerModal) {
      closeVideoModal();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && Elements.videoPlayerModal.classList.contains("active")) {
      closeVideoModal();
    }
  });
}

function openVideoModal(title, videoSrc) {
  Elements.modalVideoTitle.textContent = title;
  Elements.modalVideoElement.src = videoSrc;
  Elements.videoPlayerModal.classList.add("active");
  Elements.modalVideoElement.play().catch(() => {});
}

function closeVideoModal() {
  Elements.modalVideoElement.pause();
  Elements.modalVideoElement.src = "";
  Elements.videoPlayerModal.classList.remove("active");
}

// ==========================================================================
// KEYBOARD SHORTCUTS
// ==========================================================================
function initKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    // Ctrl+V: Auto-paste and analyze if on single view
    if ((e.ctrlKey || e.metaKey) && e.key === "v" && State.currentView === "view-single") {
      // Let native paste work on focused input
      if (document.activeElement === Elements.singleUrlInput) return;

      navigator.clipboard.readText().then(text => {
        if (text && (text.includes("tiktok.com") || text.includes("douyin.com"))) {
          Elements.singleUrlInput.value = text.trim();
          showToast("Đã dán và bắt đầu phân tích", "info");
          analyzeSingleVideo(text.trim());
        }
      }).catch(() => {});
    }
  });
}

// ==========================================================================
// NAVIGATION & TITLEBAR
// ==========================================================================
function initElectronTitlebar() {
  if (window.electronAPI) {
    Elements.winMinBtn.addEventListener("click", () => window.electronAPI.minimize());
    Elements.winMaxBtn.addEventListener("click", () => window.electronAPI.maximize());
    Elements.winCloseBtn.addEventListener("click", () => window.electronAPI.close());
  } else {
    Elements.winMinBtn.addEventListener("click", () => showToast("Đang chạy trên trình duyệt", "info"));
    Elements.winMaxBtn.addEventListener("click", () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
      } else {
        document.exitFullscreen().catch(() => {});
      }
    });
    Elements.winCloseBtn.addEventListener("click", () => showToast("Đóng tab để thoát", "info"));
  }
}

function initNavigation() {
  Elements.navItems.forEach(item => {
    item.addEventListener("click", () => {
      const targetView = item.getAttribute("data-view");
      State.currentView = targetView;
      Elements.navItems.forEach(i => i.classList.toggle("active", i.getAttribute("data-view") === targetView));
      Elements.viewPanes.forEach(p => p.classList.toggle("active", p.id === targetView));
      if (targetView === "view-downloads") loadDownloads();
    });
  });
}

// ── Bootstrap ──
document.addEventListener("DOMContentLoaded", () => {
  initElectronTitlebar();
  initNavigation();
  initSingleView();
  initBatchView();
  initDownloadsView();
  initSettingsView();
  initVideoModal();
  initKeyboardShortcuts();
  initEngineConnection();
});
