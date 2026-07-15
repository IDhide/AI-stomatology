// Киоск: связывает WebSocket-бэкенд, микрофон, плеер и визуализатор.
import { Visualizer } from "/visuals.js";
import { MicCapture, PcmPlayer } from "/audio.js";

const $ = (s) => document.querySelector(s);
const idleVideo = $("#idle-video");
const idleFallback = $("#idle-fallback");
const sceneCanvas = $("#scene");
const caption = $("#caption");
const statusEl = $("#status");
const startBtn = $("#start-btn");

const STATUS_TEXT = {
  idle: "режим ожидания",
  listening: "слушаю",
  thinking: "думаю",
  speaking: "говорю",
};

let ws, viz, mic, player;
let sessionActive = false;
let serverState = "idle";
let silenceTimer = null;
const SILENCE_END_MS = 10000; // из ТЗ: 10 секунд молчания → конец разговора

// ── Загрузка видео с медузами (если файл есть) ──────────────────────
idleVideo.src = "/assets/jellyfish.mp4";
idleVideo.addEventListener("error", () => idleVideo.classList.add("hidden"));

function showIdle() {
  sceneCanvas.classList.add("hidden");
  idleVideo.classList.toggle("hidden", !idleVideo.currentSrc);
  idleFallback.classList.remove("hidden");
  caption.classList.remove("show");
  statusEl.textContent = STATUS_TEXT.idle;
}

function showActive() {
  sceneCanvas.classList.remove("hidden");
  idleVideo.classList.add("hidden");
  idleFallback.classList.add("hidden");
}

function setCaption(text) {
  caption.textContent = text;
  caption.classList.add("show");
}

// ── Таймер «10 секунд молчания» ─────────────────────────────────────
function armSilenceTimer() {
  clearSilenceTimer();
  silenceTimer = setTimeout(() => { if (sessionActive) endSession(); }, SILENCE_END_MS);
}
function clearSilenceTimer() {
  if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
}

// ── Управление сессией ──────────────────────────────────────────────
function startSession() {
  if (sessionActive) return;
  sessionActive = true;
  showActive();
  send({ type: "presence", present: true }); // сервер инициирует приветствие
}

function endSession() {
  if (!sessionActive) return;
  sessionActive = false;
  clearSilenceTimer();
  mic?.setEnabled(false);
  send({ type: "presence", present: false }); // сервер прощается
}

// ── WebSocket ───────────────────────────────────────────────────────
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.binaryType = "arraybuffer";

  ws.onmessage = (ev) => {
    if (ev.data instanceof ArrayBuffer) {
      player.push(ev.data);            // TTS-аудио → колонка + амплитуда шара
      return;
    }
    const msg = JSON.parse(ev.data);
    handleServer(msg);
  };
  ws.onclose = () => setTimeout(connect, 1500); // авто-reconnect
}

function send(obj) {
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function handleServer(msg) {
  switch (msg.type) {
    case "state": {
      serverState = msg.value;
      viz.setState(msg.value);
      // Микрофон слушаем только когда система ждёт ответа пациента
      const listen = sessionActive && msg.value === "idle";
      // «idle» внутри активной сессии — это «слушаю пациента», не режим ожидания
      statusEl.textContent = listen ? "слушаю, говорите" : (STATUS_TEXT[msg.value] ?? msg.value);
      mic?.setEnabled(listen);
      if (listen) armSilenceTimer(); else clearSilenceTimer();
      break;
    }
    case "transcript":
      // реплика пациента — можно не показывать, но полезно при отладке
      break;
    case "reply":
      setCaption(msg.text);
      break;
    case "speak_end":
      break;
  }
}

// ── Запуск (по клику — иначе браузер не даст микрофон/звук) ──────────
// Бейдж «демо-режим», если сервер работает на заглушках (нет API-ключей)
async function showMockBadgeIfNeeded() {
  try {
    const h = await (await fetch("/health")).json();
    const mocks = ["llm", "stt", "tts"].filter((k) => h[k] === "mock");
    if (mocks.length) {
      const b = document.createElement("div");
      b.id = "mock-badge";
      b.textContent = `демо-режим: нет ключей для ${mocks.join(", ")}`;
      document.body.appendChild(b);
    }
  } catch { /* сервер недоступен — переподключение покажет */ }
}

async function boot() {
  startBtn.remove();
  showMockBadgeIfNeeded();
  viz = new Visualizer(sceneCanvas);

  player = new PcmPlayer((amp) => viz.setAmplitude(amp));
  await player.resume();

  mic = new MicCapture({
    onUtteranceStart: () => { clearSilenceTimer(); send({ type: "utterance_start" }); },
    onChunk: (pcm) => { if (ws?.readyState === WebSocket.OPEN) ws.send(pcm.buffer); },
    onUtteranceEnd: () => send({ type: "utterance_end" }),
  });
  await mic.init();

  connect();
  showIdle();
}

startBtn.addEventListener("click", boot);

// ── Отладочная панель (тест на MacBook без камеры) ──────────────────
$("#debug").addEventListener("click", (e) => {
  const act = e.target.dataset.act;
  if (act === "enter") startSession();
  else if (act === "leave") endSession();
  else if (act === "talk") mic?.setEnabled(true);
});
