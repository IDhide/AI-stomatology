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

  // ── Медузы — объёмные, с физикой щупалец ──────────────
  function hexRGB(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgba(r, g, b, a) { return `rgba(${r},${g},${b},${a})`; }
  function bright(r, g, b, k) {
    return [Math.min(255, r + k), Math.min(255, g + k), Math.min(255, b + k)];
  }

  const PALETTE = ["#9366ff", "#3ecfff", "#ff6eb4", "#ffb347", "#66ffc2", "#c084fc"];
  const jellies = [];
  let _prevT = 0;

  function makeJelly(x, y, depth) {
    const size = 30 + depth * 70 + Math.random() * 30;
    const color = PALETTE[Math.floor(Math.random() * PALETTE.length)];
    const nTent = 6 + Math.floor(Math.random() * 5);
    const tentacles = [];
    for (let i = 0; i < nTent; i++) {
      const segs = [];
      const len = 8 + Math.floor(Math.random() * 7);
      for (let j = 0; j < len; j++) segs.push({ x: x, y: y + j * 4, ox: x, oy: y + j * 4 });
      tentacles.push({
        segs,
        off: (i - (nTent - 1) / 2) / ((nTent - 1) / 2),
        w: 0.6 + Math.random() * 1.8,
      });
    }
    return {
      x, y, vx: 0, vy: 0, size, color, depth,
      phase: Math.random() * Math.PI * 2,
      pulsePhase: Math.random() * Math.PI * 2,
      pulse: 0, angle: 0, tentacles,
    };
  }

  function initJellies() {
    const w = window.innerWidth, h = window.innerHeight;
    jellies.length = 0;
    for (let i = 0; i < 7; i++) {
      const depth = 0.25 + Math.random() * 0.75;
      jellies.push(makeJelly(Math.random() * w, Math.random() * h, depth));
    }
    jellies.sort((a, b) => a.depth - b.depth);
  }

  function updateJelly(j, t, dt, w, h) {
    const spd = dt / 16;
    const p = Math.sin(t * 0.0018 + j.pulsePhase);
    j.pulse = p * (0.18 + 0.06 * Math.sin(t * 0.0005));
    const thrust = p > 0.3 ? (p - 0.3) * 0.06 * j.depth : 0;
    j.vy += (-0.015 - thrust) * j.depth * spd;
    j.vx += Math.sin(t * 0.00025 + j.phase) * 0.008 * spd;
    j.vx *= 0.993; j.vy *= 0.996;
    j.x += j.vx * spd; j.y += j.vy * spd;
    j.angle += (j.vx * 0.015 - j.angle * 0.03) * spd;
    if (j.y < -j.size * 5) { j.y = h + j.size * 3; j.x = Math.random() * w; }
    if (j.x < -j.size * 3) j.x = w + j.size * 2;
    if (j.x > w + j.size * 3) j.x = -j.size * 2;

    const bw = j.size * (1 - j.pulse * 0.35);
    const grav = 0.06 * spd, damp = Math.pow(0.97, spd);
    for (const tn of j.tentacles) {
      const s = tn.segs;
      s[0].x = j.x + tn.off * bw * 0.9;
      s[0].y = j.y + j.size * 0.08;
      for (let i = 1; i < s.length; i++) {
        const dx = s[i].x - s[i].ox, dy = s[i].y - s[i].oy;
        s[i].ox = s[i].x; s[i].oy = s[i].y;
        s[i].x += dx * damp + Math.sin(t * 0.002 + i * 0.6 + tn.off * 3) * 0.4 * spd;
        s[i].y += dy * damp + grav;
      }
      const segLen = j.size * 0.22;
      for (let iter = 0; iter < 3; iter++) {
        for (let i = 1; i < s.length; i++) {
          const a = s[i - 1], b = s[i];
          const ddx = b.x - a.x, ddy = b.y - a.y;
          const dist = Math.sqrt(ddx * ddx + ddy * ddy) || 0.001;
          const diff = (dist - segLen) / dist * 0.5;
          if (i === 1) { b.x -= ddx * diff * 2; b.y -= ddy * diff * 2; }
          else { a.x += ddx * diff; a.y += ddy * diff; b.x -= ddx * diff; b.y -= ddy * diff; }
        }
      }
    }
  }

  function drawJelly(ctx, j, t) {
    const [cr, cg, cb] = hexRGB(j.color);
    const alpha = 0.25 + j.depth * 0.55;
    const bw = j.size * (1 - j.pulse * 0.35);
    const bh = j.size * (0.75 + j.pulse * 0.12);
    const cx = j.x, cy = j.y;
    const top = cy - bh;

    ctx.save();

    // щупальца (рисуем ДО купола для глубины)
    for (const tn of j.tentacles) {
      const s = tn.segs;
      if (s.length < 2) continue;
      ctx.beginPath();
      ctx.moveTo(s[0].x, s[0].y);
      for (let i = 1; i < s.length - 1; i++) {
        const mx = (s[i].x + s[i + 1].x) / 2, my = (s[i].y + s[i + 1].y) / 2;
        ctx.quadraticCurveTo(s[i].x, s[i].y, mx, my);
      }
      ctx.lineTo(s[s.length - 1].x, s[s.length - 1].y);
      const grad = ctx.createLinearGradient(s[0].x, s[0].y, s[s.length - 1].x, s[s.length - 1].y);
      grad.addColorStop(0, rgba(cr, cg, cb, alpha * 0.5));
      grad.addColorStop(1, rgba(cr, cg, cb, 0));
      ctx.strokeStyle = grad;
      ctx.lineWidth = tn.w * (1 + j.pulse * 0.4);
      ctx.lineCap = "round";
      ctx.stroke();
    }

    // внешнее свечение
    ctx.shadowColor = rgba(cr, cg, cb, alpha * 0.5);
    ctx.shadowBlur = j.size * 0.6;

    // купол — безье-форма
    ctx.beginPath();
    ctx.moveTo(cx - bw, cy);
    ctx.bezierCurveTo(cx - bw, cy - bh * 0.5, cx - bw * 0.55, top, cx, top);
    ctx.bezierCurveTo(cx + bw * 0.55, top, cx + bw, cy - bh * 0.5, cx + bw, cy);
    ctx.bezierCurveTo(cx + bw * 0.65, cy + bh * 0.12, cx - bw * 0.65, cy + bh * 0.12, cx - bw, cy);
    ctx.closePath();

    // заливка — плотный центр, светящиеся края
    const rg = ctx.createRadialGradient(cx, cy - bh * 0.35, j.size * 0.05,
                                        cx, cy - bh * 0.25, bw * 1.15);
    rg.addColorStop(0, rgba(cr, cg, cb, alpha * 0.9));
    rg.addColorStop(0.35, rgba(cr, cg, cb, alpha * 0.45));
    rg.addColorStop(0.65, rgba(...bright(cr, cg, cb, 50), alpha * 0.6));
    rg.addColorStop(0.85, rgba(...bright(cr, cg, cb, 80), alpha * 0.7));
    rg.addColorStop(1, rgba(cr, cg, cb, 0.02));
    ctx.fillStyle = rg;
    ctx.fill();
    ctx.shadowBlur = 0;

    // внутренняя мембрана (кольцо у края — объём)
    ctx.beginPath();
    const iw = bw * 0.92, ih = bh * 0.92, itop = cy - ih;
    ctx.moveTo(cx - iw, cy - bh * 0.05);
    ctx.bezierCurveTo(cx - iw, cy - ih * 0.45, cx - iw * 0.52, itop, cx, itop);
    ctx.bezierCurveTo(cx + iw * 0.52, itop, cx + iw, cy - ih * 0.45, cx + iw, cy - bh * 0.05);
    const [lr, lg, lb] = bright(cr, cg, cb, 100);
    ctx.strokeStyle = rgba(lr, lg, lb, alpha * 0.35);
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // блик — объёмный свет
    const sx = cx - bw * 0.25, sy = top + bh * 0.28;
    const sg = ctx.createRadialGradient(sx, sy, 0, sx, sy, bw * 0.35);
    sg.addColorStop(0, rgba(255, 255, 255, alpha * 0.35));
    sg.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = sg;
    ctx.beginPath();
    ctx.ellipse(sx, sy, bw * 0.28, bh * 0.18, -0.35, 0, Math.PI * 2);
    ctx.fill();

    // второй мелкий блик
    const s2x = cx + bw * 0.15, s2y = top + bh * 0.18;
    const sg2 = ctx.createRadialGradient(s2x, s2y, 0, s2x, s2y, bw * 0.12);
    sg2.addColorStop(0, rgba(255, 255, 255, alpha * 0.2));
    sg2.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = sg2;
    ctx.beginPath();
    ctx.ellipse(s2x, s2y, bw * 0.1, bh * 0.07, -0.2, 0, Math.PI * 2);
    ctx.fill();

    // нижний ободок — складки (пульсируют)
    ctx.beginPath();
    const folds = 12;
    for (let i = 0; i <= folds; i++) {
      const frac = i / folds;
      const fx = cx - bw + frac * bw * 2;
      const fy = cy + Math.sin(frac * Math.PI * 4 + t * 0.003 + j.phase) * bh * 0.06;
      i === 0 ? ctx.moveTo(fx, fy) : ctx.lineTo(fx, fy);
    }
    ctx.strokeStyle = rgba(...bright(cr, cg, cb, 60), alpha * 0.4);
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.restore();
  }

  function drawBg(t) {
    if (jelly.style.display === "block") return;
    const w = window.innerWidth, h = window.innerHeight;
    const dt = _prevT ? t - _prevT : 16;
    _prevT = t;

    const g = bctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "#060915");
    g.addColorStop(0.45, "#0a0f24");
    g.addColorStop(1, "#04050b");
    bctx.fillStyle = g;
    bctx.fillRect(0, 0, w, h);

    for (const p of particles) {
      p.y -= p.s;
      p.tw += 0.03;
      if (p.y < -5) { p.y = h + 5; p.x = Math.random() * w; }
      const a = 0.3 + 0.3 * Math.sin(p.tw);
      bctx.beginPath();
      bctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      bctx.fillStyle = rgba(180, 210, 255, a);
      bctx.fill();
    }

    for (const j of jellies) {
      updateJelly(j, t, dt, w, h);
      drawJelly(bctx, j, t);
    }
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
