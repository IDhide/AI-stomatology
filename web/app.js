/* ============================================================
   Smile.AI — клиентская логика киоска
   • аудио-волна в круге (canvas), реагирует на «амплитуду» речи
   • процедурный фон (медузы/частицы) когда нет видеофайла
   • синхронизация состояния через SSE (/api/events)
   • режимы: idle · greeting · listening · thinking · speaking
   ============================================================ */

(() => {
  "use strict";

  const body = document.body;
  const statusLabel = document.getElementById("status-label");
  const subtitleEl = document.getElementById("subtitle");
  const hudText = document.getElementById("hud-text");
  const jelly = document.getElementById("jellyfish");

  const STATUS_RU = {
    idle: "",
    greeting: "Здравствуйте",
    listening: "Слушаю…",
    thinking: "Думаю…",
    speaking: "Говорю…",
  };

  // ── Глобальное состояние ────────────────────────────────
  const state = {
    mode: "idle",
    amplitude: 0,      // 0..1 целевая
    ampSmooth: 0,      // сглаженная
    speaking: false,
  };

  function setMode(mode) {
    if (!STATUS_RU.hasOwnProperty(mode)) return;
    state.mode = mode;
    body.dataset.mode = mode;
    statusLabel.textContent = STATUS_RU[mode];
    hudText.textContent = mode.toUpperCase();
    state.speaking = mode === "speaking";
  }

  function setSubtitle(text, who) {
    if (!text) {
      subtitleEl.classList.remove("show");
      return;
    }
    subtitleEl.textContent = text;
    subtitleEl.classList.remove("user", "bot");
    subtitleEl.classList.add(who === "user" ? "user" : "bot", "show");
  }

  // ============================================================
  //  Аудио-волна в круге
  // ============================================================
  const wave = document.getElementById("wave");
  const wctx = wave.getContext("2d");

  function sizeWave() {
    const dpr = window.devicePixelRatio || 1;
    const r = wave.getBoundingClientRect();
    wave.width = Math.max(2, r.width * dpr);
    wave.height = Math.max(2, r.height * dpr);
    wctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function drawWave(t) {
    const r = wave.getBoundingClientRect();
    const W = r.width, H = r.height;
    wctx.clearRect(0, 0, W, H);

    const cy = H / 2;
    // амплитуда зависит от режима
    let amp;
    if (state.mode === "speaking") {
      amp = 0.10 + state.ampSmooth * 0.40;
    } else if (state.mode === "listening") {
      amp = 0.05 + 0.03 * Math.sin(t / 600);
    } else if (state.mode === "thinking") {
      amp = 0.03;
    } else {
      amp = 0.06 + 0.02 * Math.sin(t / 700);
    }
    const A = H * amp;

    // несколько наложенных синусоид → «живая» дорожка
    const draw = (alpha, lw, phase, freq, scale) => {
      wctx.beginPath();
      for (let x = 0; x <= W; x += 2) {
        const p = x / W;
        // огибающая: тоньше к краям круга
        const env = Math.sin(Math.PI * p);
        const y =
          cy +
          env * A * scale *
            (Math.sin(p * freq * Math.PI * 2 + t / 200 + phase) * 0.7 +
             Math.sin(p * freq * 1.7 * Math.PI * 2 - t / 320 + phase) * 0.3);
        x === 0 ? wctx.moveTo(x, y) : wctx.lineTo(x, y);
      }
      wctx.strokeStyle = `rgba(255,255,255,${alpha})`;
      wctx.lineWidth = lw;
      wctx.lineJoin = "round";
      wctx.lineCap = "round";
      wctx.shadowColor = "rgba(255,255,255,0.55)";
      wctx.shadowBlur = 12;
      wctx.stroke();
      wctx.shadowBlur = 0;
    };

    draw(0.95, 2.2, 0, 3, 1.0);
    draw(0.35, 1.4, 1.1, 5, 0.6);
    draw(0.18, 1.0, 2.3, 8, 0.4);
  }

  // ============================================================
  //  Процедурный фон (медузы/частицы) — fallback без видео
  // ============================================================
  const bg = document.getElementById("bg-canvas");
  const bctx = bg.getContext("2d");
  let particles = [];

  function sizeBg() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    bg.width = window.innerWidth * dpr;
    bg.height = window.innerHeight * dpr;
    bctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    initParticles();
  }

  function initParticles() {
    const w = window.innerWidth, h = window.innerHeight;
    const count = Math.round((w * h) / 9000);
    particles = [];
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * 1.8 + 0.3,
        s: Math.random() * 0.25 + 0.05,
        tw: Math.random() * Math.PI * 2,
      });
    }
  }

  // несколько «медуз» — мягкие светящиеся купола, медленно всплывают
  const jellies = [];
  function initJellies() {
    const w = window.innerWidth, h = window.innerHeight;
    jellies.length = 0;
    const palette = ["#8a5cff", "#4bd6ff", "#ff8fc7", "#ffd27a"];
    for (let i = 0; i < 5; i++) {
      jellies.push({
        x: Math.random() * w,
        y: Math.random() * h,
        r: 40 + Math.random() * 70,
        s: 6 + Math.random() * 14,
        c: palette[i % palette.length],
        ph: Math.random() * Math.PI * 2,
      });
    }
  }

  function drawBg(t) {
    if (jelly.style.display === "block") return; // есть реальное видео
    const w = window.innerWidth, h = window.innerHeight;

    // глубокий градиент
    const g = bctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "#070a18");
    g.addColorStop(0.55, "#0a0f24");
    g.addColorStop(1, "#05060d");
    bctx.fillStyle = g;
    bctx.fillRect(0, 0, w, h);

    // звёзды
    for (const p of particles) {
      p.y -= p.s;
      p.tw += 0.03;
      if (p.y < -5) { p.y = h + 5; p.x = Math.random() * w; }
      const a = 0.35 + 0.35 * Math.sin(p.tw);
      bctx.beginPath();
      bctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      bctx.fillStyle = `rgba(190,210,255,${a})`;
      bctx.fill();
    }

    // медузы — мягкие купола со щупальцами
    for (const j of jellies) {
      j.y -= j.s * 0.012;
      if (j.y < -j.r * 2) { j.y = h + j.r * 2; j.x = Math.random() * w; }
      const bob = Math.sin(t / 1000 + j.ph) * 8;
      const cx = j.x, cy = j.y + bob;

      const rg = bctx.createRadialGradient(cx, cy, 2, cx, cy, j.r);
      rg.addColorStop(0, hexA(j.c, 0.55));
      rg.addColorStop(0.6, hexA(j.c, 0.18));
      rg.addColorStop(1, hexA(j.c, 0));
      bctx.fillStyle = rg;
      bctx.beginPath();
      bctx.arc(cx, cy, j.r, Math.PI, 0);           // купол
      bctx.fill();

      // щупальца
      bctx.strokeStyle = hexA(j.c, 0.25);
      bctx.lineWidth = 1.5;
      for (let k = -3; k <= 3; k++) {
        bctx.beginPath();
        const sx = cx + k * (j.r / 5);
        bctx.moveTo(sx, cy);
        for (let s = 0; s <= 6; s++) {
          const yy = cy + s * (j.r / 3);
          const xx = sx + Math.sin(t / 500 + s + k) * 6;
          bctx.lineTo(xx, yy);
        }
        bctx.stroke();
      }
    }
  }

  function hexA(hex, a) {
    const n = parseInt(hex.slice(1), 16);
    const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
    return `rgba(${r},${g},${b},${a})`;
  }

  // ============================================================
  //  Главный цикл анимации
  // ============================================================
  function loop(t) {
    // сглаживание амплитуды
    state.ampSmooth += (state.amplitude - state.ampSmooth) * 0.18;
    if (state.mode === "speaking") {
      // если внешняя амплитуда не приходит — генерим «речевую» огибающую
      if (state._extAmpAt === undefined || t - state._extAmpAt > 400) {
        state.amplitude = 0.35 + 0.45 * Math.abs(Math.sin(t / 140)) * Math.random();
      }
    } else {
      state.amplitude = 0;
    }

    drawBg(t);
    drawWave(t);
    requestAnimationFrame(loop);
  }

  // ============================================================
  //  Подключение к серверу (SSE)
  // ============================================================
  function connect() {
    let es;
    try {
      es = new EventSource("/api/events");
    } catch (e) {
      console.warn("SSE недоступен, остаюсь в демо-режиме фона", e);
      return;
    }
    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        handleEvent(msg);
      } catch (_) {}
    };
    es.onerror = () => { hudText.textContent = state.mode.toUpperCase() + " (offline)"; };
  }

  function handleEvent(msg) {
    if (msg.type === "mode") setMode(msg.mode);
    else if (msg.type === "subtitle") setSubtitle(msg.text, msg.who);
    else if (msg.type === "amplitude") {
      state.amplitude = Math.max(0, Math.min(1.2, msg.value));
      state._extAmpAt = performance.now();
    } else if (msg.type === "clear_subtitle") setSubtitle("");
  }

  // ── Видео медуз, если файл доступен ─────────────────────
  function tryVideo() {
    const src = "/assets/jellyfish.mp4";
    fetch(src, { method: "HEAD" })
      .then((r) => {
        if (r.ok) {
          jelly.src = src;
          jelly.style.display = "block";
          jelly.play().catch(() => {});
        }
      })
      .catch(() => {});
  }

  // ── init ────────────────────────────────────────────────
  function resizeAll() { sizeBg(); sizeWave(); initJellies(); }
  window.addEventListener("resize", resizeAll);

  // ручной триггер для отладки без сервера: клавиши 1..5
  window.addEventListener("keydown", (e) => {
    const map = { "1": "idle", "2": "greeting", "3": "listening", "4": "thinking", "5": "speaking" };
    if (map[e.key]) setMode(map[e.key]);
  });

  sizeBg();
  sizeWave();
  initJellies();
  setMode("idle");
  tryVideo();
  connect();
  requestAnimationFrame(loop);

  // экспорт для скриншот-скриптов / отладки
  window.SmileUI = { setMode, setSubtitle, state };
})();
