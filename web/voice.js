/* ============================================================
   voice.js — голосовой режим Оливии в браузере
   Три пути ввода (выбирается автоматически):
     1) Chrome/Edge — Web Speech API (SpeechRecognition), распознавание в браузере
     2) Firefox и др. — MediaRecorder → POST /api/stt (распознавание на сервере)
     3) Если сервер-STT недоступен — строка ввода текстом (Оливия отвечает голосом)

   Везде Оливия отвечает голосом через speechSynthesis (TTS).
   Цикл: приветствие → СЛУШАЮ → ДУМАЮ → ГОВОРЮ → снова СЛУШАЮ. Esc — стоп.
   ============================================================ */

(() => {
  "use strict";

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const hasRecorder =
    !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia &&
       window.MediaRecorder);
  const hudText = document.getElementById("hud-text");

  const ui = () => window.SmileUI;
  const setMode = (m) => ui() && ui().setMode(m);
  const setSub = (t, who) => ui() && ui().setSubtitle(t, who);

  const state = {
    active: false,
    speaking: false,
    ruVoice: null,
    rec: null,
    inputMode: "none",     // sr | server | text
    serverTTS: null,       // true | false (определяется при старте)
    audioEl: null,         // <audio> для воспроизведения серверного TTS
  };

  // ── русский голос для TTS ───────────────────────────────
  function pickVoice() {
    const voices = window.speechSynthesis.getVoices() || [];
    state.ruVoice =
      voices.find((v) => /ru[-_]RU/i.test(v.lang)) ||
      voices.find((v) => /^ru/i.test(v.lang)) ||
      voices.find((v) => /russian|русск/i.test(v.name)) || null;
  }

  // ── TTS: серверный Piper, фолбэк — speechSynthesis браузера ──
  function speak(text) {
    return new Promise((resolve) => {
      if (!text) return resolve();
      setMode("speaking");
      setSub(text, "bot");
      state.speaking = true;

      const done = () => { state.speaking = false; resolve(); };
      // подстраховка: гарантированно вернуть управление
      const safety = setTimeout(done,
        Math.min(20000, 380 * text.split(/\s+/).length + 2000));

      if (state.serverTTS) {
        // серверный Piper: качаем WAV и проигрываем
        const url = "/api/tts?text=" + encodeURIComponent(text);
        try { state.audioEl && state.audioEl.pause(); } catch (_) {}
        const a = new Audio(url);
        state.audioEl = a;
        a.onended = () => { clearTimeout(safety); done(); };
        a.onerror = () => {
          clearTimeout(safety);
          console.warn("[voice] server TTS error → fallback на браузерный");
          state.serverTTS = false;
          speakBrowser(text).then(done);
        };
        a.play().catch(() => {
          clearTimeout(safety);
          state.serverTTS = false;
          speakBrowser(text).then(done);
        });
      } else {
        speakBrowser(text).then(() => { clearTimeout(safety); done(); });
      }
    });
  }

  function speakBrowser(text) {
    return new Promise((resolve) => {
      try { window.speechSynthesis.cancel(); } catch (_) {}
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "ru-RU";
      if (state.ruVoice) u.voice = state.ruVoice;
      u.rate = 1.0; u.pitch = 1.05;
      u.onend = () => resolve();
      u.onerror = () => resolve();
      window.speechSynthesis.speak(u);
    });
  }

  // ── общий шаг: отправить текст пациента → ответ голосом ──
  // Возвращает true, если Оливия ответила; false — если реплику проигнорировали
  // (нерелевантная/фоновая речь — тогда молчим и продолжаем слушать).
  async function respondTo(said) {
    if (!said) return false;
    setMode("thinking");
    hudText.textContent = "THINKING…";
    let data = {};
    try {
      const r = await fetch("/api/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: said }),
      });
      data = await r.json();
    } catch (_) {
      data = { reply: "Извините, связь прервалась. Повторите, пожалуйста?" };
    }
    if (data.ignored || !data.reply) {
      // нерелевантная речь — не показываем её и молчим
      setSub("", "user");
      return false;
    }
    setSub("вы: " + said, "user");
    await speak(data.reply);
    return true;
  }

  // ════════════════════════════════════════════════════════
  //  Путь 1: Web Speech API (Chrome/Edge)
  // ════════════════════════════════════════════════════════
  function listenSR() {
    return new Promise((resolve) => {
      setMode("listening");
      hudText.textContent = "LISTENING 🎤";
      const rec = new SR();
      state.rec = rec;
      rec.lang = "ru-RU";
      rec.interimResults = true;
      rec.maxAlternatives = 1;
      rec.continuous = false;
      let finalText = "", done = false;
      const finish = (t) => { if (done) return; done = true;
        try { rec.stop(); } catch (_) {} resolve((t || "").trim()); };
      rec.onresult = (e) => {
        let interim = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          if (r.isFinal) finalText += r[0].transcript; else interim += r[0].transcript;
        }
        if (interim) setSub("вы: " + interim, "user");
        if (finalText) finish(finalText);
      };
      rec.onerror = (e) => {
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          hudText.textContent = "НЕТ ДОСТУПА К МИКРОФОНУ"; state.active = false;
        }
        finish(finalText);
      };
      rec.onend = () => finish(finalText);
      try { rec.start(); } catch (_) { finish(""); }
    });
  }

  // ════════════════════════════════════════════════════════
  //  Путь 2: MediaRecorder → сервер (Firefox)
  // ════════════════════════════════════════════════════════
  async function recordUntilSilence(maxMs = 8000, silenceMs = 1200) {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    let mime = "audio/webm";
    if (!MediaRecorder.isTypeSupported(mime)) {
      mime = MediaRecorder.isTypeSupported("audio/ogg") ? "audio/ogg" : "";
    }
    const mr = mime ? new MediaRecorder(stream, { mimeType: mime })
                    : new MediaRecorder(stream);
    const chunks = [];
    mr.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };

    // VAD на Web Audio: ждём тишину silenceMs после речи
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const srcNode = ac.createMediaStreamSource(stream);
    const an = ac.createAnalyser(); an.fftSize = 2048;
    srcNode.connect(an);
    const buf = new Uint8Array(an.fftSize);

    mr.start();
    const t0 = Date.now();
    let lastVoice = Date.now(), heardVoice = false;

    return await new Promise((resolve) => {
      const timer = setInterval(() => {
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
        const rms = Math.sqrt(sum / buf.length);
        const now = Date.now();
        if (rms > 0.04) { lastVoice = now; heardVoice = true; }
        const silentLongEnough = heardVoice && (now - lastVoice > silenceMs);
        if (silentLongEnough || now - t0 > maxMs) {
          clearInterval(timer);
          try { mr.stop(); } catch (_) {}
        }
      }, 100);
      mr.onstop = () => {
        try { ac.close(); } catch (_) {}
        stream.getTracks().forEach((t) => t.stop());
        resolve({ blob: new Blob(chunks, { type: mr.mimeType || "audio/webm" }),
                  heardVoice });
      };
    });
  }

  async function listenServer() {
    setMode("listening");
    hudText.textContent = "LISTENING 🎤";
    let rec;
    try {
      rec = await recordUntilSilence();
    } catch (e) {
      hudText.textContent = "НЕТ ДОСТУПА К МИКРОФОНУ";
      state.active = false;
      return { text: "", unavailable: true };
    }
    if (!rec.heardVoice || rec.blob.size < 1200) return { text: "" };
    setMode("thinking");
    hudText.textContent = "РАСПОЗНАЮ…";
    try {
      const r = await fetch("/api/stt", {
        method: "POST",
        headers: { "Content-Type": rec.blob.type || "audio/webm" },
        body: rec.blob,
      });
      if (r.status === 503) return { text: "", unavailable: true };
      return { text: ((await r.json()).text || "").trim() };
    } catch (_) {
      return { text: "" };
    }
  }

  // ════════════════════════════════════════════════════════
  //  Путь 3: ввод текстом (фолбэк)
  // ════════════════════════════════════════════════════════
  let textBar = null;
  function enableTextMode(note) {
    state.inputMode = "text";
    if (textBar) { textBar.style.display = "flex"; return; }
    textBar = document.createElement("form");
    textBar.id = "text-input-bar";
    textBar.innerHTML =
      '<input id="ti" type="text" autocomplete="off" ' +
      'placeholder="Напишите сообщение Оливии и нажмите Enter…" />' +
      '<button type="submit">→</button>';
    document.body.appendChild(textBar);
    const inp = textBar.querySelector("#ti");
    textBar.addEventListener("submit", async (e) => {
      e.preventDefault();
      const v = inp.value.trim();
      if (!v) return;
      inp.value = "";
      await respondTo(v);
      setMode("listening");
      hudText.textContent = "ВВЕДИТЕ СООБЩЕНИЕ";
      inp.focus();
    });
    inp.focus();
    if (note) console.warn("[voice] текстовый режим:", note);
  }

  // ── главный цикл ────────────────────────────────────────
  async function loopVoice(listenFn) {
    while (state.active) {
      const res = await listenFn();
      if (!state.active) break;
      if (res && res.unavailable) {
        await speak("Распознавание речи сейчас недоступно. Напишите, пожалуйста, " +
                    "сообщение в строке внизу, а я отвечу голосом.");
        enableTextMode("stt unavailable");
        return;
      }
      const said = typeof res === "string" ? res : (res ? res.text : "");
      if (!said) continue;          // тишина — слушаем снова
      await respondTo(said);
    }
    setMode("idle");
    hudText.textContent = "IDLE";
  }

  // ── запуск (по жесту пользователя) ──────────────────────
  async function start(source) {
    if (state.active) return;
    state.active = true;

    try {
      const r = await fetch("/api/tts/status");
      state.serverTTS = !!(await r.json()).available;
    } catch (_) { state.serverTTS = false; }
    console.log("[voice] server TTS:", state.serverTTS ? "Piper" : "browser");

    const greetUrl = source === "camera"
      ? "/api/greeting?source=camera"
      : "/api/greeting";
    let greet = "Здравствуйте, меня зовут Оливия. Чем могу помочь?";
    try { greet = (await (await fetch(greetUrl)).json()).text || greet; } catch (_) {}
    await speak(greet);

    if (SR) {
      state.inputMode = "sr";
      loopVoice(listenSR);
    } else if (hasRecorder) {
      state.inputMode = "server";
      loopVoice(listenServer);
    } else {
      enableTextMode("no SR, no MediaRecorder");
      setMode("listening");
      hudText.textContent = "ВВЕДИТЕ СООБЩЕНИЕ";
    }
  }

  function stop() {
    state.active = false;
    try { window.speechSynthesis.cancel(); } catch (_) {}
    try { state.audioEl && state.audioEl.pause(); } catch (_) {}
    try { state.rec && state.rec.stop(); } catch (_) {}
    setMode("idle");
  }

  // ── серверная камера (SSE) ─────────────────────────────
  function connectCamera() {
    const es = new EventSource("/api/events");
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d.type !== "camera") return;
        if (d.event === "person_detected" && !state.active) {
          const ov = document.getElementById("start-overlay");
          if (ov) { ov.classList.add("hide"); setTimeout(() => ov.remove(), 600); }
          start("camera");
        } else if (d.event === "person_left" && state.active) {
          stop();
        }
      } catch (_) {}
    };
  }

  // ── оверлей старта ──────────────────────────────────────
  function buildOverlay() {
    if (document.getElementById("start-overlay")) return;
    const hint = SR
      ? "разрешите доступ к микрофону"
      : (hasRecorder
          ? "распознавание на сервере · разрешите доступ к микрофону"
          : "введите сообщение текстом — Оливия ответит голосом");
    const ov = document.createElement("div");
    ov.id = "start-overlay";
    ov.innerHTML =
      '<div class="ov-inner">' +
      '<div class="ov-circle"></div>' +
      '<div class="ov-title">Коснитесь экрана, чтобы поговорить с Оливией</div>' +
      '<div class="ov-sub">администратор клиники «Стоматология №1» · ' + hint + "</div>" +
      "</div>";
    ov.addEventListener("click", () => {
      ov.classList.add("hide");
      setTimeout(() => ov.remove(), 600);
      start();
    });
    document.body.appendChild(ov);
  }

  window.addEventListener("keydown", (e) => { if (e.key === "Escape") stop(); });

  if ("speechSynthesis" in window) {
    pickVoice();
    window.speechSynthesis.onvoiceschanged = pickVoice;
  }

  window.SmileVoice = { start, stop, state };

  function init() { buildOverlay(); connectCamera(); }
  document.addEventListener("DOMContentLoaded", init);
  if (document.readyState !== "loading") init();
})();
