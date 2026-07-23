// Киоск: связывает WebSocket-бэкенд, микрофон, плеер и сцену «Океан Оливии».
// Сцена работает непрерывно (режим ожидания = живой подводный мир); переход в
// активный режим происходит внутри одной сцены, без смены страницы (ТЗ §12).
import { OceanScene, loadConfig, autoQuality } from "/visuals.js";
import { MicCapture, PcmPlayer } from "/audio.js";

const $ = (s) => document.querySelector(s);
const sceneCanvas = $("#scene");
const idleFallback = $("#idle-fallback");
const caption = $("#caption");
const statusEl = $("#status");
const startBtn = $("#start-btn");

const STATUS_TEXT = {
  idle: "", listening: "слушаю", thinking: "думаю", speaking: "говорю", greeting: "",
};

let ws, viz, mic, player;
let sessionActive = false;
let silenceTimer = null;
const SILENCE_END_MS = 10000; // 10 секунд молчания → конец разговора

function setCaption(text) {
  if (!text) { caption.classList.remove("show"); return; }
  caption.textContent = text;
  caption.classList.add("show");
}
function setStatus(state) {
  statusEl.textContent = STATUS_TEXT[state] ?? "";
}

// ── Таймер «10 секунд молчания» ─────────────────────────────────────
function armSilenceTimer() {
  clearSilenceTimer();
  silenceTimer = setTimeout(() => { if (sessionActive) endSession(); }, SILENCE_END_MS);
}
function clearSilenceTimer() {
  if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
}

// ── Управление сессией (присутствие человека) ───────────────────────
function startSession() {
  if (sessionActive) return;
  sessionActive = true;
  viz?.setPresence(true);              // ядро → активная сфера (awakening)
  send({ type: "presence", present: true });
}

function endSession() {
  if (!sessionActive) return;
  sessionActive = false;
  clearSilenceTimer();
  mic?.setEnabled(false);
  viz?.setPresence(false);             // прощание → возврат в ожидание
  setCaption("");
  send({ type: "presence", present: false });
}

// ── WebSocket ───────────────────────────────────────────────────────
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  ws.onmessage = (ev) => {
    if (ev.data instanceof ArrayBuffer) { player.push(ev.data); return; }
    try { handleServer(JSON.parse(ev.data)); } catch (_) {}
  };
  ws.onclose = () => setTimeout(connect, 1500); // авто-reconnect; сцена не прерывается
  ws.onerror = () => {};
}

function send(obj) {
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function handleServer(msg) {
  switch (msg.type) {
    case "state": {
      const v = msg.value;
      setStatus(v);
      viz?.setState(v);
      // Микрофон слушаем, когда система ждёт ответа пациента
      const listen = sessionActive && v === "idle";
      mic?.setEnabled(listen);
      if (listen) armSilenceTimer(); else clearSilenceTimer();
      break;
    }
    case "presence":
      if (msg.value) startSession(); else endSession();
      break;
    case "reply":
      setCaption(msg.text);
      break;
    case "speak_end":
    case "transcript":
      break;
  }
}

// ── Запуск (по клику — иначе браузер не даст микрофон/звук) ──────────
async function boot() {
  startBtn.remove();
  idleFallback.classList.add("hidden");

  const cfg = await loadConfig();
  if (!cfg.quality) cfg.quality = autoQuality();

  try {
    viz = new OceanScene(sceneCanvas, cfg);
    sceneCanvas.classList.remove("hidden");
    if (location.search.includes("debug")) window.__ocean = viz; // ручной прогон состояний
  } catch (e) {
    console.error("WebGL недоступен — включён запасной фон", e);
    idleFallback.classList.remove("hidden"); // CSS-fallback (ТЗ §24)
    return;
  }

  player = new PcmPlayer((amp) => viz.setAmplitude(amp));
  await player.resume();

  // Каждый кадр отдаём сфере реальные уровни воспроизводимого аудио (§16).
  const feedAudio = () => {
    if (player) viz.setAudioLevels(player.getLevels());
    requestAnimationFrame(feedAudio);
  };
  requestAnimationFrame(feedAudio);

  mic = new MicCapture({
    onUtteranceStart: () => { clearSilenceTimer(); send({ type: "utterance_start" }); },
    onChunk: (pcm) => { if (ws?.readyState === WebSocket.OPEN) ws.send(pcm.buffer); },
    onUtteranceEnd: () => send({ type: "utterance_end" }),
  });
  try { await mic.init(); } catch (_) { /* без микрофона сцена всё равно работает */ }

  connect();
}

startBtn.addEventListener("click", boot);

// ── Отладочная панель (тест без камеры), включается через ?debug ─────
if (location.search.includes("debug")) $("#debug").classList.add("on");
$("#debug").addEventListener("click", (e) => {
  const act = e.target.dataset.act;
  if (act === "enter") { startSession(); viz?.setState("greeting"); }
  else if (act === "leave") endSession();
  else if (act === "talk") { viz?.setState("listening"); mic?.setEnabled(true); }
});
