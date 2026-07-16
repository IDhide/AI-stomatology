// Киоск: связывает WebSocket-бэкенд, микрофон, плеер и визуализатор.
import { Visualizer } from "/visuals.js";
import { MicCapture, PcmPlayer } from "/audio.js";
import { JellyfishScene } from "/jellyfish.js";

const $ = (s) => document.querySelector(s);
const idleVideo = $("#idle-video");
const idleCanvas = $("#idle-canvas");
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

let ws, viz, mic, player, jelly, wakeRec;
let sessionActive = false;
let serverState = "idle";
let videoOk = false;
let silenceTimer = null;
const SILENCE_END_MS = 10000; // из ТЗ: 10 секунд молчания → конец разговора

// ── Своё видео с медузами приоритетнее canvas-сцены (если файл есть) ─
idleVideo.src = "/assets/jellyfish.mp4";
idleVideo.addEventListener("canplay", () => { videoOk = true; if (!sessionActive) showIdle(); });
idleVideo.addEventListener("error", () => { videoOk = false; });

function showIdle() {
  sceneCanvas.classList.add("hidden");
  if (videoOk) {
    idleVideo.classList.remove("hidden");
    idleCanvas.classList.add("hidden");
    jelly?.stop();
  } else {
    idleVideo.classList.add("hidden");
    idleCanvas.classList.remove("hidden");
    jelly?.start();
  }
  caption.classList.remove("show");
  statusEl.textContent = wakeRec ? "скажите «Оливия», чтобы начать" : STATUS_TEXT.idle;
}

function showActive() {
  sceneCanvas.classList.remove("hidden");
  idleVideo.classList.add("hidden");
  idleCanvas.classList.add("hidden");
  jelly?.stop();
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
  document.body.classList.add("in-dialog"); // курсор прячем только в диалоге
  stopWakeWord();
  showActive();
  send({ type: "presence", present: true }); // сервер инициирует приветствие
}

function endSession() {
  if (!sessionActive) return;
  sessionActive = false;
  document.body.classList.remove("in-dialog");
  clearSilenceTimer();
  mic?.setEnabled(false);
  send({ type: "presence", present: false }); // сервер прощается
  startWakeWord();
}

// ── Wake word «Оливия» (Web Speech API, работает в Chrome) ──────────
const WAKE_WORDS = ["оливия", "оливи", "аливия", "аливи", "olivia"];

function startWakeWord() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return; // нет поддержки — остаются кнопки/камера
  if (!wakeRec) {
    wakeRec = new SR();
    wakeRec.lang = "ru-RU";
    wakeRec.continuous = true;
    wakeRec.interimResults = true;
    wakeRec.onresult = (e) => {
      if (sessionActive) return;
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const text = e.results[i][0].transcript.toLowerCase();
        if (WAKE_WORDS.some((w) => text.includes(w))) {
          startSession();
          return;
        }
      }
    };
    // Chrome сам останавливает распознавание — перезапускаем, пока ждём
    wakeRec.onend = () => {
      if (!sessionActive && wakeRec) {
        setTimeout(() => { try { wakeRec.start(); } catch {} }, 300);
      }
    };
    wakeRec.onerror = () => {};
  }
  try { wakeRec.start(); } catch {}
}

function stopWakeWord() {
  try { wakeRec?.stop(); } catch {}
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
      // Микрофон включён и в idle (ждём фразу), и в listening (фраза идёт!).
      // Выключаем только пока Оливия думает или говорит — иначе, получив от
      // сервера state=listening, мы бы сами обрывали запись на первом кадре.
      const micOn = sessionActive && (msg.value === "idle" || msg.value === "listening");
      statusEl.textContent =
        sessionActive && msg.value === "idle"
          ? "слушаю, говорите"
          : (STATUS_TEXT[msg.value] ?? msg.value);
      mic?.setEnabled(micOn);
      // Таймер «10 секунд тишины» — только пока ждём начала фразы
      if (sessionActive && msg.value === "idle") armSilenceTimer();
      else clearSilenceTimer();
      // Прощание закончилось → плавный возврат к медузам
      if (!sessionActive && msg.value === "idle") showIdle();
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
  jelly = new JellyfishScene(idleCanvas);
  viz = new Visualizer(sceneCanvas);

  player = new PcmPlayer(
    (amp) => viz.setAmplitude(amp),
    (bands) => viz.setBands(bands),
  );
  await player.resume();

  mic = new MicCapture({
    onUtteranceStart: () => { clearSilenceTimer(); send({ type: "utterance_start" }); },
    onChunk: (pcm) => { if (ws?.readyState === WebSocket.OPEN) ws.send(pcm.buffer); },
    onUtteranceEnd: () => send({ type: "utterance_end" }),
    onUtteranceCancel: () => send({ type: "utterance_cancel" }),
  });
  await mic.init();

  connect();
  startWakeWord();
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
