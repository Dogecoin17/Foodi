const $ = (id) => document.getElementById(id);
const fmt = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const api = async (path, opts) => {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};

let schedule = [];

function renderTemp(t) {
  $("temp").textContent = t != null ? Math.round(t) : "–";
}

let videoStarted = false;
function renderVideo(mode) {
  const card = $("videocard");
  if (mode === "none") { card.style.display = "none"; return; }
  card.style.display = "";
  if (videoStarted) return;
  videoStarted = true;
  if (mode === "live") {
    $("video").remove(); // MJPEG can't play in <video>; use <img>
    const img = $("liveimg");
    img.style.display = "";
    img.src = "/api/video?t=" + Date.now();
  } else {
    $("liveimg").remove();
    $("video").src = "/api/video";
  }
}

function renderStatus(s) {
  $("conn").textContent = s.connected ? "feeder connected" : "feeder offline";
  $("conn").className = "pill " + (s.connected ? "ok" : "bad");
  $("weight").textContent = s.weight_g ?? "–";
  $("level").textContent = s.food_level_pct ?? "–";
  $("fstate").textContent = (s.state || "–").toLowerCase().replace("_", " ");
  if ("temp_c" in s) renderTemp(s.temp_c);
  if (s.video) renderVideo(s.video);
}

function renderSchedule() {
  $("schedule").innerHTML = "";
  schedule.forEach((e, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${fmt(e.minute_of_day)} – ${e.grams} g</span>`;
    const del = document.createElement("button");
    del.className = "ghost"; del.textContent = "remove";
    del.onclick = async () => { schedule.splice(i, 1); await saveSchedule(); };
    li.appendChild(del);
    $("schedule").appendChild(li);
  });
}

async function saveSchedule() {
  schedule = await api("/api/schedule", { method: "PUT", body: JSON.stringify(schedule) });
  renderSchedule();
}

function listInto(id, items, text) {
  $(id).innerHTML = items.length ? "" : "<li><small>nothing yet</small></li>";
  items.forEach((x) => { const li = document.createElement("li"); li.textContent = text(x); $(id).appendChild(li); });
}

async function refresh() {
  renderStatus(await api("/api/status"));
  schedule = await api("/api/schedule"); renderSchedule();
  listInto("events", await api("/api/events?limit=10"),
    (e) => `${new Date(e.ts * 1000).toLocaleString()} – ${e.actual_g} g (${e.source})`);
  listInto("alerts", await api("/api/alerts?limit=10"),
    (a) => `${new Date(a.ts * 1000).toLocaleString()} – ${a.message}`);
  const ins = await api("/api/insights");
  $("insights").textContent = ins.anomalies.length ? ins.anomalies.map((a) => a.message).join(" ") : "No observations yet.";
  drawChart(await api("/api/history/daily?days=30"));
}

function drawChart(days) {
  const cv = $("chart");
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = 120;
  cv.width = w * dpr; cv.height = h * dpr;
  const ctx = cv.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  if (!days.length) return;
  const max = Math.max(...days.map((d) => d.grams), 1);
  const style = getComputedStyle(document.documentElement);
  const accent = style.getPropertyValue("--accent").trim() || "#e8743b";
  const muted = style.getPropertyValue("--muted").trim() || "#6b7280";
  const bw = w / days.length;
  days.forEach((d, i) => {
    const bh = (d.grams / max) * (h - 18);
    const low = d.grams < 0.7 * (days.reduce((s, x) => s + x.grams, 0) / days.length);
    ctx.fillStyle = low ? "#c0392b" : accent;
    ctx.fillRect(i * bw + 1, h - bh, bw - 2, bh);
  });
  ctx.fillStyle = muted;
  ctx.font = "10px system-ui";
  ctx.fillText(days[0].date.slice(5), 2, h - 2);
  const last = days[days.length - 1].date.slice(5);
  ctx.fillText(last, w - ctx.measureText(last).width - 2, h - 2);
}

$("feed").onclick = async () => {
  try { await api("/api/feed", { method: "POST", body: JSON.stringify({ grams: +$("grams").value }) }); }
  catch (e) { alert(e.message); }
};

$("add").onclick = async () => {
  const [h, m] = $("time").value.split(":").map(Number);
  schedule.push({ minute_of_day: h * 60 + m, grams: +$("sgrams").value, days_mask: 127 });
  await saveSchedule();
};

function connectWs() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    const d = JSON.parse(ev.data);
    if (d.type === "telemetry") renderStatus({ connected: true, ...d });
    else if (d.type === "system") renderTemp(d.temp_c);
    else refresh();
  };
  ws.onclose = () => setTimeout(connectWs, 2000);
}

refresh().catch(console.error);
connectWs();

// Hide the live-view card if the clip is missing (404).
$("video").addEventListener("error", () => {
  $("videocard").style.display = "none";
});
