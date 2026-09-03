import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const initialBatch = { status: "", percent: 0, message: "", subtext: "" };
const initialSingle = { status: "", percent: 0, filename: "", message: "" };
const repositoryUrl = "https://github.com/hunterv9/Dowloadapi";

function Icon({ name, size = 18 }) {
  const paths = {
    download: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></>,
    bolt: <><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></>,
    search: <><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></>,
    user: <><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></>,
    folder: <><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68h.01A1.65 1.65 0 0 0 10 3.17V3a2 2 0 1 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.32 9h.01A1.65 1.65 0 0 0 20.84 10H21a2 2 0 1 1 0 4h-.09A1.65 1.65 0 0 0 19.4 15z" /></>,
    list: <><line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" /><line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" /></>,
    play: <polygon points="5 3 19 12 5 21 5 3" />,
    trash: <><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></>,
    refresh: <><polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" /><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" /></>,
    close: <><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></>,
    minimize: <line x1="5" y1="12" x2="19" y2="12" />,
    maximize: <rect x="6" y="6" width="12" height="12" rx="1" />,
    github: <><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3.3-.4 6.8-1.6 6.8-7A5.4 5.4 0 0 0 19.3 3.8 5 5 0 0 0 19.2 1S18.1.6 15 2.6a13.4 13.4 0 0 0-6 0C5.9.6 4.8 1 4.8 1A5 5 0 0 0 4.7 3.8a5.4 5.4 0 0 0-1.5 3.7c0 5.4 3.5 6.6 6.8 7A4.8 4.8 0 0 0 9 18v4" /><path d="M9 18c-4.5 2-5-2-7-2" /></>,
    link: <><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" /></>,
    save: <><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" /></>,
  };
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function Toast({ toast }) {
  if (!toast) return null;
  return <div className={`toast toast-${toast.type}`}><span className="toast-dot" />{toast.message}</div>;
}

function App() {
  const [view, setView] = useState("single");
  const [connection, setConnection] = useState("connecting");
  const [config, setConfig] = useState({});
  const [downloads, setDownloads] = useState([]);
  const [downloadSize, setDownloadSize] = useState(0);
  const [search, setSearch] = useState("");
  const [singleUrl, setSingleUrl] = useState("");
  const [videoInfo, setVideoInfo] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [single, setSingle] = useState(initialSingle);
  const [profile, setProfile] = useState("");
  const [maxVideos, setMaxVideos] = useState("0");
  const [customDir, setCustomDir] = useState("");
  const [bulkUrls, setBulkUrls] = useState("");
  const [scannedProfile, setScannedProfile] = useState(null);
  const [scanCount, setScanCount] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [batch, setBatch] = useState(initialBatch);
  const [saving, setSaving] = useState(false);
  const [modal, setModal] = useState(null);
  const [toast, setToast] = useState(null);
  const [updateInfo, setUpdateInfo] = useState(null);
  const socketRef = useRef(null);
  const progressWsRef = useRef(null);
  const callbacksRef = useRef(new Map());
  const requestIdRef = useRef(1);
  const retryRef = useRef(null);
  const isDesktop = Boolean(window.electronAPI) || window.location.protocol === "file:";

  const openRepository = (event) => {
    if (window.electronAPI?.openExternal) {
      event.preventDefault();
      window.electronAPI.openExternal().catch(() => window.open(repositoryUrl, "_blank", "noopener,noreferrer"));
    }
  };

  const notify = (message, type = "info") => {
    setToast({ message, type });
    window.clearTimeout(notify.timer);
    notify.timer = window.setTimeout(() => setToast(null), 3600);
  };

  const loadDownloads = async () => {
    try {
      const data = await sendAction("GET_DOWNLOADS");
      setDownloads(data.files || []);
      setDownloadSize(data.total_size_mb || 0);
    } catch (error) {
      console.error(error);
    }
  };

  const pollSingle = (taskId) => {
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`/api/task-status/${taskId}`);
        if (!response.ok) throw new Error("Không thể đọc tiến độ");
        const data = await response.json();
        setSingle((current) => ({ ...current, percent: data.progress || 0, filename: data.filename || current.filename }));
        if (data.status === "completed" || data.status === "failed") {
          window.clearInterval(timer);
          if (data.status === "completed") {
            notify("Tải video thành công", "success");
            loadDownloads();
          } else notify(data.error || "Tải video thất bại", "error");
        }
      } catch (error) {
        window.clearInterval(timer);
        notify(error.message, "error");
      }
    }, 600);
  };

  const pollBatch = (taskId) => {
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`/api/task-status/${taskId}`);
        if (!response.ok) throw new Error("Không thể đọc tiến độ");
        const data = await response.json();
        setBatch((current) => ({
          ...current,
          percent: data.progress || 0,
          status: data.status,
          message: data.message || current.message,
          subtext: data.status === "resolving" ? "Đang tìm video trong profile..." : current.subtext,
        }));
        if (data.status === "completed" || data.status === "failed") {
          window.clearInterval(timer);
          if (data.status === "completed") {
            notify("Tải hàng loạt thành công", "success");
            loadDownloads();
          } else notify(data.error || "Tải hàng loạt thất bại", "error");
        }
      } catch (error) {
        window.clearInterval(timer);
        notify(error.message, "error");
      }
    }, 800);
  };

  const handleServerMessage = (message) => {
    if (message.id && callbacksRef.current.has(message.id)) {
      const callback = callbacksRef.current.get(message.id);
      callbacksRef.current.delete(message.id);
      if (message.status === "error") callback.reject(new Error(message.error));
      else callback.resolve(message.data);
      return;
    }
    if (message.event === "DOWNLOAD_PROGRESS") {
      setSingle((current) => ({ ...current, percent: message.percent || 0, message: "Đang tải dữ liệu..." }));
    } else if (message.event === "DOWNLOAD_COMPLETED") {
      setSingle({ status: "completed", percent: 100, filename: message.result?.filename || "Video", message: "Đã lưu video vào thư viện" });
      notify("Tải video thành công", "success");
      loadDownloads();
    } else if (message.event === "DOWNLOAD_FAILED") {
      setSingle((current) => ({ ...current, status: "failed", message: message.error || "Tải thất bại" }));
      notify(message.error || "Tải video thất bại", "error");
    } else if (message.event === "BATCH_PROGRESS") {
      const percent = message.total ? Math.round((message.index / message.total) * 100) : 0;
      setBatch({ status: "downloading", percent, message: message.message || "Đang xử lý...", subtext: `Đã xử lý ${message.index || 0}/${message.total || 0} video` });
    } else if (message.event === "BATCH_COMPLETED") {
      setBatch({ status: "completed", percent: 100, message: "Hoàn tất", subtext: `Đã lưu ${message.result?.downloaded || 0} video` });
      notify("Tải hàng loạt thành công", "success");
      loadDownloads();
    } else if (message.event === "BATCH_FAILED") {
      setBatch((current) => ({ ...current, status: "failed", message: "Không thể tải hàng loạt", subtext: message.error || "Đã xảy ra lỗi" }));
      notify(message.error || "Tải hàng loạt thất bại", "error");
    }
  };

  const restAction = async (action, payload) => {
    const routes = {
      GET_CONFIG: ["/api/config", "GET"],
      GET_DOWNLOADS: ["/api/downloads", "GET"],
      SAVE_CONFIG: ["/api/config", "POST"],
      ANALYZE_VIDEO: ["/api/video-info", "POST"],
      SCAN_PROFILE: ["/api/scan-profile", "POST"],
      DOWNLOAD_SINGLE: ["/api/download-single", "POST"],
      DOWNLOAD_PROFILE: ["/api/download-profile", "POST"],
      OPEN_FOLDER: ["/api/open-folder", "POST"],
      OPEN_FILE: ["/api/open-file", "POST"],
      DELETE_DOWNLOAD: ["/api/delete-download", "POST"],
    };
    const [route, method] = routes[action];
    const body = action === "ANALYZE_VIDEO" || action === "SCAN_PROFILE" ? { url: payload.url } : action === "DOWNLOAD_SINGLE" ? { url: payload.url } : action === "DOWNLOAD_PROFILE" ? { profile: payload.profile, urls: payload.urls || null, max_videos: payload.max_videos || 0, custom_dir: payload.custom_dir || null } : action === "OPEN_FILE" || action === "DELETE_DOWNLOAD" ? { path: payload.path } : action === "SAVE_CONFIG" ? payload : undefined;
    const response = await fetch(route, { method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined });
    let data;
    try {
      data = await response.json();
    } catch (error) {
      throw new Error("Web engine chưa chạy. Hãy khởi động FastAPI rồi tải lại trang.");
    }
    if (!response.ok) throw new Error(data.detail || data.error || "Yêu cầu thất bại");
    if (action === "GET_CONFIG") return data;
    if (action === "ANALYZE_VIDEO") return data.data;
    if (action === "DOWNLOAD_SINGLE") { pollSingle(data.task_id); return data; }
    if (action === "DOWNLOAD_PROFILE") { pollBatch(data.task_id); return data; }
    return data;
  };

  const sendAction = (action, payload = {}) => new Promise((resolve, reject) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      const id = requestIdRef.current++;
      callbacksRef.current.set(id, { resolve, reject });
      socket.send(JSON.stringify({ id, action, payload }));
      return;
    }
    if (isDesktop) {
      reject(new Error("Engine đang khởi động, vui lòng thử lại sau giây lát."));
      return;
    }
    restAction(action, payload).then(resolve).catch(reject);
  });

  const connect = () => {
    let socket;
    try {
      socket = new WebSocket("ws://127.0.0.1:8765");
      socketRef.current = socket;
      socket.onopen = () => {
        setConnection("connected");
        if (retryRef.current) window.clearTimeout(retryRef.current);
        retryRef.current = null;
        sendAction("GET_CONFIG").then((data) => {
          setConfig(data.config || {});
          loadDownloads();
        }).catch((error) => notify(error.message, "error"));
      };
      socket.onmessage = (event) => {
        try { handleServerMessage(JSON.parse(event.data)); } catch (error) { console.error(error); }
      };
      socket.onerror = () => {
        if (isDesktop) setConnection("connecting");
        else setConnection("rest");
      };
      socket.onclose = () => {
        socketRef.current = null;
        if (isDesktop) {
          setConnection("connecting");
          if (!retryRef.current) retryRef.current = window.setTimeout(() => { retryRef.current = null; connect(); }, 1000);
        } else setConnection("rest");
      };
    } catch (error) {
      if (isDesktop) retryRef.current = window.setTimeout(connect, 1000);
      else setConnection("rest");
    }
  };

  useEffect(() => {
    connect();
    if (!isDesktop) {
      loadInitialRest();
      connectProgressWs();
      checkVersion();
    }
    return () => {
      if (retryRef.current) window.clearTimeout(retryRef.current);
      socketRef.current?.close();
      progressWsRef.current?.close();
    };
  }, []);

  const loadInitialRest = async () => {
    try {
      const data = await restAction("GET_CONFIG", {});
      setConfig(data.config || {});
      await loadDownloads();
    } catch (error) {
      setConnection("rest");
      notify(error.message, "error");
    }
  };

  // ── WebSocket progress connection (REST mode only) ──────────────────────
  const connectProgressWs = () => {
    if (isDesktop) return; // Desktop uses its own WS
    try {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${proto}//${window.location.host}/ws/progress`);
      progressWsRef.current = ws;
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.event === "DOWNLOAD_PROGRESS") {
            setSingle((c) => ({ ...c, percent: msg.percent || 0, message: "Đang tải dữ liệu..." }));
          } else if (msg.event === "DOWNLOAD_COMPLETED") {
            setSingle({ status: "completed", percent: 100, filename: msg.result?.filename || "Video", message: "Đã lưu video vào thư viện" });
            notify("Tải video thành công", "success");
            loadDownloads();
          } else if (msg.event === "DOWNLOAD_FAILED") {
            setSingle((c) => ({ ...c, status: "failed", message: msg.error || "Tải thất bại" }));
            notify(msg.error || "Tải video thất bại", "error");
          } else if (msg.event === "BATCH_PROGRESS") {
            const pct = msg.percent || (msg.total ? Math.round((msg.index / msg.total) * 100) : 0);
            setBatch({ status: "downloading", percent: pct, message: msg.message || "Đang xử lý...", subtext: `Đã xử lý ${msg.index || 0}/${msg.total || 0} video` });
          } else if (msg.event === "BATCH_COMPLETED") {
            setBatch({ status: "completed", percent: 100, message: "Hoàn tất", subtext: `Đã lưu ${msg.result?.downloaded || 0} video` });
            notify("Tải hàng loạt thành công", "success");
            loadDownloads();
          } else if (msg.event === "BATCH_FAILED") {
            setBatch((c) => ({ ...c, status: "failed", message: "Không thể tải hàng loạt", subtext: msg.error || "Đã xảy ra lỗi" }));
            notify(msg.error || "Tải hàng loạt thất bại", "error");
          }
        } catch (e) { console.error(e); }
      };
      ws.onclose = () => { progressWsRef.current = null; };
    } catch (e) { /* silent */ }
  };

  // ── Version check ──────────────────────────────────────────────────────
  const checkVersion = async () => {
    try {
      const resp = await fetch("/api/version");
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.update_available) {
        setUpdateInfo(data);
        notify(`Có phiên bản mới v${data.latest}!`, "info");
      }
    } catch (e) { /* silent */ }
  };

  const analyze = async () => {
    if (!singleUrl.trim()) return notify("Vui lòng nhập liên kết video", "warning");
    setAnalyzing(true);
    setVideoInfo(null);
    try { setVideoInfo(await sendAction("ANALYZE_VIDEO", { url: singleUrl.trim() })); notify("Phân tích thành công", "success"); }
    catch (error) { notify(error.message, "error"); }
    finally { setAnalyzing(false); }
  };

  const startSingle = async () => {
    if (!videoInfo) return;
    setSingle({ status: "downloading", percent: 0, filename: "", message: "Đang kết nối máy chủ CDN..." });
    try { await sendAction("DOWNLOAD_SINGLE", { url: videoInfo.url || singleUrl.trim() }); }
    catch (error) { setSingle((current) => ({ ...current, status: "failed", message: error.message })); notify(error.message, "error"); }
  };

  const scan = async () => {
    if (!profile.trim()) return notify("Vui lòng nhập username hoặc link profile", "warning");
    setScanning(true);
    try {
      const data = await sendAction("SCAN_PROFILE", { url: profile.trim() });
      setScannedProfile({ profile: profile.trim(), urls: data.urls || [] });
      setScanCount(data.count || 0);
      setMaxVideos(String(data.count || 0));
      notify(`Đã tìm thấy ${data.count || 0} video`, "success");
    } catch (error) { notify(error.message, "error"); }
    finally { setScanning(false); }
  };

  const startBatch = async (type) => {
    if (type === "bulk" && !bulkUrls.trim()) return notify("Vui lòng dán ít nhất một đường link", "warning");
    if (type === "profile" && !profile.trim()) return notify("Vui lòng nhập username hoặc link profile", "warning");
    const limit = Number.parseInt(maxVideos, 10) || 0;
    let payload;
    if (type === "bulk") {
      payload = { profile: "bulk_list", urls: bulkUrls.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean) };
    } else {
      const scannedUrls = scannedProfile?.profile === profile.trim() ? scannedProfile.urls : undefined;
      payload = { profile: profile.trim(), urls: scannedUrls && limit ? scannedUrls.slice(0, limit) : scannedUrls, max_videos: limit, custom_dir: customDir.trim() || undefined };
    }
    setBatch({ status: "resolving", percent: 0, message: "Đang khởi tạo...", subtext: "Đang gửi yêu cầu..." });
    try { await sendAction("DOWNLOAD_PROFILE", payload); notify("Đã bắt đầu tải hàng loạt", "info"); }
    catch (error) { setBatch((current) => ({ ...current, status: "failed", message: "Không thể bắt đầu", subtext: error.message })); notify(error.message, "error"); }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const result = await sendAction("SAVE_CONFIG", { download_dir: config.download_dir || "", video_quality: config.video_quality || "hd", save_metadata: config.save_metadata !== false, custom_cookie_string: config.custom_cookie_string || "" });
      setConfig(result.config || result);
      notify("Đã lưu cấu hình", "success");
    } catch (error) { notify(error.message, "error"); }
    finally { setSaving(false); }
  };

  const filteredDownloads = downloads.filter((item) => [item.name, item.title, item.author].some((value) => String(value || "").toLowerCase().includes(search.toLowerCase())));
  const changeProfile = (value) => { setProfile(value); if (scannedProfile && scannedProfile.profile !== value.trim()) { setScannedProfile(null); setScanCount(null); } };

  return <div className="app-shell">
    {updateInfo && <div className="update-banner"><span>🚀 Có phiên bản mới <strong>v{updateInfo.latest}</strong> — <a href={updateInfo.url || repositoryUrl + "/releases/latest"} target="_blank" rel="noreferrer">Tải ngay</a></span><button onClick={() => setUpdateInfo(null)} aria-label="Đóng"><Icon name="close" size={14} /></button></div>}
    <header className="topbar">
      <div className="brand"><img className="brand-logo" src="./favicon.ico" alt="" /><div><strong>INFRABASES</strong><span>VIDEO WORKSPACE</span></div></div>
      <a className="repo-link" href={repositoryUrl} target="_blank" rel="noreferrer" onClick={openRepository} aria-label="Mở repository GitHub" title="Mở repository GitHub"><Icon name="github" size={17} /></a>
      {window.electronAPI && <div className="window-actions"><button onClick={() => window.electronAPI.minimize()} aria-label="Thu nhỏ" title="Thu nhỏ"><Icon name="minimize" size={14} /></button><button onClick={() => window.electronAPI.maximize()} aria-label="Phóng to" title="Phóng to"><Icon name="maximize" size={13} /></button><button onClick={() => window.electronAPI.close()} aria-label="Đóng" title="Đóng"><Icon name="close" size={14} /></button></div>}
    </header>
    <div className="layout">
      <aside className="sidebar">
        <div className="side-label">WORKSPACE</div>
        <NavButton active={view === "single"} icon="download" text="Video đơn lẻ" onClick={() => setView("single")} />
        <NavButton active={view === "batch"} icon="list" text="Tải hàng loạt" onClick={() => setView("batch")} />
        <NavButton active={view === "library"} icon="folder" text="Thư viện" badge={downloads.length} onClick={() => { setView("library"); loadDownloads(); }} />
        <div className="side-label side-label-lower">SYSTEM</div>
        <NavButton active={view === "settings"} icon="settings" text="Cấu hình" onClick={() => setView("settings")} />
      </aside>
      <main className="content">
        {view === "single" && <SingleView url={singleUrl} setUrl={setSingleUrl} info={videoInfo} analyzing={analyzing} analyze={analyze} start={startSingle} state={single} />}
        {view === "batch" && <BatchView profile={profile} setProfile={changeProfile} maxVideos={maxVideos} setMaxVideos={setMaxVideos} customDir={customDir} setCustomDir={setCustomDir} bulkUrls={bulkUrls} setBulkUrls={setBulkUrls} scan={scan} scanning={scanning} scanCount={scanCount} startBatch={startBatch} batch={batch} />}
        {view === "library" && <LibraryView downloads={filteredDownloads} total={downloads.length} size={downloadSize} search={search} setSearch={setSearch} refresh={loadDownloads} openFolder={() => sendAction("OPEN_FOLDER").then(() => notify("Đã mở thư mục", "success")).catch((error) => notify(error.message, "error"))} play={(item) => setModal({ title: item.title || item.name, src: item.stream_url || "" })} reveal={(item) => sendAction("OPEN_FILE", { path: item.path }).then(() => notify("Đã mở vị trí file", "success")).catch((error) => notify(error.message, "error"))} remove={(item) => { if (window.confirm(`Xóa video "${item.title || item.name}"?`)) sendAction("DELETE_DOWNLOAD", { path: item.path }).then(() => { notify("Đã xóa video", "success"); loadDownloads(); }).catch((error) => notify(error.message, "error")); }} />}
        {view === "settings" && <SettingsView config={config} setConfig={setConfig} save={saveSettings} saving={saving} />}
      </main>
    </div>
    {modal && <div className="modal-backdrop" onClick={(event) => event.target === event.currentTarget && setModal(null)}><div className="modal"><div className="modal-head"><strong>{modal.title}</strong><button onClick={() => setModal(null)} aria-label="Đóng"><Icon name="close" /></button></div><video src={modal.src} controls autoPlay /></div></div>}
    <Toast toast={toast} />
  </div>;
}

function NavButton({ active, icon, text, badge, onClick }) { return <button className={`nav-button ${active ? "active" : ""}`} onClick={onClick} aria-label={text} title={text}><Icon name={icon} /><span>{text}</span>{badge > 0 && <b>{badge}</b>}</button>; }

function PageHeader({ eyebrow, title, description }) { return <div className="page-header"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div></div>; }
function Button({ children, variant = "primary", onClick, disabled, icon }) { return <button className={`button button-${variant}`} onClick={onClick} disabled={disabled}>{icon && <Icon name={icon} size={16} />}{children}</button>; }
function Progress({ data, label }) { if (!data.status) return null; return <section className="progress-panel"><div className="progress-line"><strong>{label}</strong><b>{Math.round(data.percent)}%</b></div><div className="progress-track"><i style={{ width: `${data.percent}%` }} /></div><p>{data.message || data.subtext}</p><small>{data.subtext}</small></section>; }

function SingleView({ url, setUrl, info, analyzing, analyze, start, state }) {
  return <><PageHeader eyebrow="01 / QUICK CAPTURE" title="Tải video mới" description="Dán link TikTok hoặc Douyin để xem trước và tải video." /><section className="capture-panel"><div className="panel-kicker"><span className="number">01</span><span>VIDEO URL</span></div><div className="url-row"><Icon name="link" /><input value={url} onChange={(event) => setUrl(event.target.value)} onKeyDown={(event) => event.key === "Enter" && analyze()} placeholder="Dán link TikTok hoặc Douyin vào đây..." /><Button onClick={analyze} disabled={analyzing} variant="accent" icon="search">{analyzing ? "Đang phân tích" : "Phân tích"}</Button></div><div className="hint-row"><span>TIKTOK</span><span>DOUYIN</span></div></section>{info && <section className="preview-panel"><div className="preview-art">{info.thumbnail ? <img src={info.thumbnail} alt="Thumbnail" /> : <div className="preview-placeholder"><Icon name="play" size={36} /></div>}<span className="play-label">PREVIEW</span></div><div className="preview-copy"><div className="platform-tag">{info.url?.includes("douyin") ? "DOUYIN" : "TIKTOK"}</div><h2>{info.title || "Video không có tiêu đề"}</h2><p className="author"><Icon name="user" size={15} /> {info.nickname || info.uploader || "Creator"} <span>@{info.uploader || "user"}</span></p><div className="preview-actions"><Button onClick={start} icon="download">Tải Video Full HD</Button><span className="meta-note">{info.duration ? `${Math.floor(info.duration / 60)}:${String(Math.floor(info.duration % 60)).padStart(2, "0")}` : "HD"} · {info.id || "Direct stream"}</span></div></div></section>}<Progress data={state} label={state.filename || "Đang tải video"} /></>;
}

function BatchView({ profile, setProfile, maxVideos, setMaxVideos, customDir, setCustomDir, bulkUrls, setBulkUrls, scan, scanning, scanCount, startBatch, batch }) {
  return <><PageHeader eyebrow="02 / BATCH WORKSPACE" title="Tải hàng loạt" description="Tải toàn bộ kênh hoặc xử lý một danh sách link trong cùng một hàng đợi." /><div className="batch-grid"><section className="work-panel"><div className="panel-heading"><div className="panel-icon coral"><Icon name="user" /></div><div><span className="panel-index">PROFILE DOWNLOADER</span><h2>Toàn bộ kênh</h2></div></div><p className="panel-description">Quét profile TikTok hoặc Douyin, kiểm tra số lượng video rồi bắt đầu tải theo kênh.</p><div className="field-label">PROFILE OR USERNAME</div><div className="field-with-action"><input value={profile} onChange={(event) => setProfile(event.target.value)} onKeyDown={(event) => event.key === "Enter" && scan()} placeholder="@username hoặc link profile" /><Button variant="soft" onClick={scan} disabled={scanning} icon="search">{scanning ? "Đang quét" : "Quét profile"}</Button></div>{scanCount !== null && <div className="scan-result"><span className="check-mark">✓</span><strong>{scanCount} video được tìm thấy</strong><span>Danh sách đã sẵn sàng</span></div>}<div className="field-grid"><label><span>SỐ VIDEO <em>0 = tất cả</em></span><input type="number" min="0" value={maxVideos} onChange={(event) => setMaxVideos(event.target.value)} /></label><label><span>THƯ MỤC LƯU <em>tuỳ chọn</em></span><input value={customDir} onChange={(event) => setCustomDir(event.target.value)} placeholder="Mặc định" /></label></div><Button onClick={() => startBatch("profile")} icon="download">Bắt đầu tải theo kênh</Button></section><section className="work-panel"><div className="panel-heading"><div className="panel-icon mint"><Icon name="list" /></div><div><span className="panel-index">URL QUEUE</span><h2>Danh sách link</h2></div></div><p className="panel-description">Mỗi dòng một link video. Hỗ trợ link TikTok và Douyin trong cùng một danh sách.</p><div className="field-label">VIDEO URLS</div><textarea value={bulkUrls} onChange={(event) => setBulkUrls(event.target.value)} placeholder={'https://www.tiktok.com/@user/video/...\nhttps://v.douyin.com/...'} /><div className="textarea-foot"><span>{bulkUrls.split(/[\n,]+/).filter((item) => item.trim()).length} links</span><span>ENTER để thêm dòng</span></div><Button onClick={() => startBatch("bulk")} icon="bolt">Bắt đầu tải danh sách</Button></section></div><Progress data={batch} label={batch.message || "Hàng đợi tải"} /></>;
}

function LibraryView({ downloads, total, size, search, setSearch, refresh, openFolder, play, reveal, remove }) {
  return <><PageHeader eyebrow="03 / MEDIA LIBRARY" title="Thư viện media" description={`${total} video đã lưu · ${size} MB trên workspace hiện tại.`} /><div className="library-tools"><div className="search-box"><Icon name="search" size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm theo tên, tác giả..." /></div><Button variant="soft" onClick={refresh} icon="refresh">Làm mới</Button><Button variant="soft" onClick={openFolder} icon="folder">Mở thư mục</Button></div>{downloads.length === 0 ? <div className="empty-state"><Icon name="folder" size={34} /><h2>Chưa có video</h2><p>Video tải thành công sẽ xuất hiện ở đây.</p></div> : <div className="media-grid">{downloads.map((item) => <article className="media-card" key={item.path}><div className="media-thumb">{item.thumbnail ? <img src={item.thumbnail} alt="" /> : <Icon name="play" size={28} />}<span>{item.platform || "MEDIA"}</span></div><div className="media-body"><h3 title={item.title || item.name}>{item.title || item.name}</h3><p>@{item.author || "Creator"} · {item.size_mb} MB</p><div><button onClick={() => play(item)}><Icon name="play" size={13} /> Phát</button><button onClick={() => reveal(item)}><Icon name="folder" size={13} /> Vị trí</button><button className="danger" onClick={() => remove(item)} aria-label="Xóa"><Icon name="trash" size={13} /></button></div></div></article>)}</div>}</>;
}

function SettingsView({ config, setConfig, save, saving }) {
  const update = (key, value) => setConfig((current) => ({ ...current, [key]: value }));
  return <><PageHeader eyebrow="04 / SYSTEM" title="Cấu hình" description="Thiết lập thư mục lưu, chất lượng video và cookie cho phiên làm việc." /><section className="settings-panel"><label><div><strong>Thư mục lưu trữ</strong><span>Nơi lưu video, metadata và phụ đề.</span></div><input value={config.download_dir || ""} onChange={(event) => update("download_dir", event.target.value)} placeholder="Đường dẫn downloads" /></label><label><div><strong>Chất lượng video</strong><span>Độ phân giải ưu tiên khi tải.</span></div><select value={config.video_quality || "hd"} onChange={(event) => update("video_quality", event.target.value)}><option value="hd">Full HD 1080p</option><option value="standard">Standard 720p</option></select></label><label><div><strong>Lưu metadata</strong><span>Tạo file JSON cạnh mỗi video.</span></div><input className="toggle" type="checkbox" checked={config.save_metadata !== false} onChange={(event) => update("save_metadata", event.target.checked)} /></label><label className="stacked"><div><strong>Cookie thủ công</strong><span>Dùng khi nền tảng yêu cầu phiên đăng nhập.</span></div><textarea value={config.custom_cookie_string || ""} onChange={(event) => update("custom_cookie_string", event.target.value)} placeholder="sessionid=...; ttwid=..." /></label><div className="settings-actions"><Button onClick={save} disabled={saving} icon="save">{saving ? "Đang lưu" : "Lưu cấu hình"}</Button></div></section></>;
}

createRoot(document.getElementById("root")).render(<App />);
