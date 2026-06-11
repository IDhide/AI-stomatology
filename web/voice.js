/* ============================================================
   voice.js — голосовой режим Оливии (активация по кодовому слову)

   Работает как «Алиса»: киоск молча показывает заставку с медузами
   и подсказку. Пациент говорит «Оливия» → она здоровается и слушает.
   Никаких авто-приветствий по камере — ничего не раздражает.

   Фазы:
     off     — до первого касания экрана (жест нужен браузеру для микрофона)
     passive — ждём кодовое слово «Оливия» (фоновое распознавание)
     active  — диалог: СЛУШАЮ → ДУМАЮ → ГОВОРЮ → снова СЛУШАЮ

   Возврат в passive: пациент прощается, либо 3 «пустых» прослушивания
   подряд (ушёл/молчит), либо Esc.

   Пути ввода (автовыбор): Web Speech API (Chrome/Edge) → серверный STT
   (Firefox, MediaRecorder → /api/stt) → текстовая строка.
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

  // кодовое слово: «Оливия» + частые ослышки распознавалок
  const WAKE_RE = /(оливи|аливи|ол[ие]вь|olivia|oliwia)/i;
  // прощание → вернуться к заставке
  const BYE_RE = /(до свидани|всего доброго|всего хорошего|спасибо,? (это )?(всё|все)|больше ничего|это всё|это все|пока,? оливия)/i;

  const PASSIVE_HUD = "СКАЖИТЕ «ОЛИВИЯ»";
  const SILENCE_LIMIT = 3;   // пустых прослушиваний подряд → заставка

  const state = {
    phase: "off",          // off | passive | active
    speaking: false,
    ruVoice: null,
    rec: null,
    inputMode: "none",     // sr | server | text
    serverTTS: null,
    audioEl: null,
  };

  function setHint(visible) {
    document.body.classList.toggle("wake-ready", !!visible);
  }

  function setHintText(html) {
    const el = document.querySelector("#wake-hint .wh-title");
    if (el) el.innerHTML = html;
  }

  // активация по касанию экрана (надёжный путь, особенно для Firefox)
  let _tapHandler = null;
  function armTapActivation() {
    disarmTapActivation();
    _tapHandler = () => { if (state.phase === "passive") activate(""); };
    document.addEventListener("click", _tapHandler);
  }
  function disarmTapActivation() {
    if (_tapHandler) {
      document.removeEventListener("click", _tapHandler);
      _tapHandler = null;
    }
  }

  // ── русский голос для браузерного TTS (запасной путь) ────
  function pickVoice() {
    const voices = window.speechSynthesis.getVoices() || [];
    state.ruVoice =
      voices.find((v) => /ru[-_]RU/i.test(v.lang)) ||
      voices.find((v) => /^ru/i.test(v.lang)) ||
      voices.find((v) => /russian|русск/i.test(v.name)) || null;
  }

  // ── TTS: серверный (XTTS/Silero), фолбэк — браузерный ────
  function speak(text) {
    return new Promise((resolve) => {
      if (!text) return resolve();
      setMode("speaking");
      setSub(text, "bot");
      state.speaking = true;

      const done = () => { state.speaking = false; resolve(); };
      const safety = setTimeout(done,
        Math.min(30000, 380 * text.split(/\s+/).length + 4000));

      if (state.serverTTS) {
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

  // ── общий шаг: текст пациента → ответ Оливии голосом ─────
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
      setSub("", "user");
      return false;
    }
    setSub("вы: " + said, "user");
    await speak(data.reply);
    return true;
  }

  // ════════════════════════════════════════════════════════
  //  Прослушивание: Web Speech API (Chrome/Edge)
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
          hudText.textContent = "НЕТ ДОСТУПА К МИКРОФОНУ"; state.phase = "off";
        }
        finish(finalText);
      };
      rec.onend = () => finish(finalText);
      try { rec.start(); } catch (_) { finish(""); }
    });
  }

  // ── фоновое ожидание кодового слова (Chrome/Edge) ─────────
  function wakeLoopSR() {
    if (state.phase !== "passive") return;
    const rec = new SR();
    state.rec = rec;
    rec.lang = "ru-RU";
    rec.continuous = true;
    rec.interimResults = true;
    let woke = false, tailText = "";
    rec.onresult = (e) => {
      let txt = "";
      for (let i = e.resultIndex; i < e.results.length; i++)
        txt += e.results[i][0].transcript;
      if (WAKE_RE.test(txt)) {
        woke = true;
        // если сказали «Оливия, сколько стоят виниры» — хвост станет первым вопросом
        tailText = txt.split(WAKE_RE).pop().replace(/^[\s,!.…-]+/, "").trim();
        try { rec.stop(); } catch (_) {}
      }
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        state.phase = "off";
        hudText.textContent = "НЕТ ДОСТУПА К МИКРОФОНУ";
      }
    };
    rec.onend = () => {
      if (state.phase !== "passive") return;
      if (woke) activate(tailText);
      else setTimeout(wakeLoopSR, 300);  // Chrome сам глушит сессию — перезапуск
    };
    try { rec.start(); } catch (_) { setTimeout(wakeLoopSR, 1500); }
  }

  // ════════════════════════════════════════════════════════
  //  Прослушивание: MediaRecorder → сервер (Firefox)
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

  async function sttRequest(blob) {
    try {
      const r = await fetch("/api/stt", {
        method: "POST",
        headers: { "Content-Type": blob.type || "audio/webm" },
        body: blob,
      });
      if (r.status === 503) return { text: "", unavailable: true };
      return { text: ((await r.json()).text || "").trim() };
    } catch (_) {
      return { text: "" };
    }
  }

  async function listenServer() {
    setMode("listening");
    hudText.textContent = "LISTENING 🎤";
    let rec;
    try {
      rec = await recordUntilSilence();
    } catch (e) {
      hudText.textContent = "НЕТ ДОСТУПА К МИКРОФОНУ";
      state.phase = "off";
      return { text: "", unavailable: true };
    }
    if (!rec.heardVoice || rec.blob.size < 1200) return { text: "" };
    setMode("thinking");
    hudText.textContent = "РАСПОЗНАЮ…";
    return await sttRequest(rec.blob);
  }

  // ── фоновое ожидание кодового слова (Firefox / сервер) ────
  async function wakeLoopServer() {
    while (state.phase === "passive") {
      let rec;
      try {
        rec = await recordUntilSilence(5000, 900);
      } catch (_) {
        state.phase = "off";
        hudText.textContent = "НЕТ ДОСТУПА К МИКРОФОНУ";
        return;
      }
      if (state.phase !== "passive") return;
      if (!rec.heardVoice || rec.blob.size < 1200) continue;
      const res = await sttRequest(rec.blob);
      if (res.unavailable) {
        enableTextMode("stt unavailable");
        return;
      }
      const said = res.text || "";
      if (WAKE_RE.test(said)) {
        const tail = said.split(WAKE_RE).pop().replace(/^[\s,!.…-]+/, "").trim();
        activate(tail);
        return;
      }
    }
  }

  // ════════════════════════════════════════════════════════
  //  Текстовый ввод (фолбэк без микрофона)
  // ════════════════════════════════════════════════════════
  let textBar = null;
  function enableTextMode(note) {
    state.inputMode = "text";
    state.phase = "active";
    setHint(false);
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
    setMode("listening");
    hudText.textContent = "ВВЕДИТЕ СООБЩЕНИЕ";
    if (note) console.warn("[voice] текстовый режим:", note);
  }

  // ════════════════════════════════════════════════════════
  //  Фазы: passive (заставка) ⇄ active (диалог)
  // ════════════════════════════════════════════════════════
  function enterPassive() {
    state.phase = "passive";
    setMode("idle");
    setSub("");
    setHint(true);
    if (state.inputMode === "sr") {
      // Chrome/Edge: распознавание точное и лёгкое → ждём кодовое слово.
      hudText.textContent = PASSIVE_HUD;
      setHintText('Чтобы связаться с администратором,<br/>скажите — <em>«Оливия»</em>');
      wakeLoopSR();
    } else {
      // Firefox/сервер: непрерывный whisper ради wake-слова — нагрузка на CPU
      // и ненадёжно (мис-слышит «Оливию»). Активируем касанием экрана.
      hudText.textContent = "КОСНИТЕСЬ ЭКРАНА";
      setHintText('Коснитесь экрана,<br/>чтобы позвать <em>Оливию</em>');
      armTapActivation();
    }
  }

  async function activate(firstUtterance) {
    if (state.phase === "active") return;
    state.phase = "active";
    setHint(false);
    disarmTapActivation();

    let greet = "Здравствуйте! Меня зовут Оливия. Чем могу вам помочь?";
    try { greet = (await (await fetch("/api/greeting")).json()).text || greet; } catch (_) {}
    await speak(greet);

    if (firstUtterance && firstUtterance.length > 2) {
      await respondTo(firstUtterance);
    }

    const listenFn = state.inputMode === "sr" ? listenSR : listenServer;
    let silences = 0;
    while (state.phase === "active") {
      const res = await listenFn();
      if (state.phase !== "active") break;
      if (res && res.unavailable) { enableTextMode("stt unavailable"); return; }
      const said = (typeof res === "string" ? res : (res ? res.text : "")) || "";
      if (!said) {
        silences++;
        if (silences >= SILENCE_LIMIT) break;   // молчит/ушёл → заставка
        continue;
      }
      silences = 0;
      if (BYE_RE.test(said)) {
        setSub("вы: " + said, "user");
        await speak("Хорошего дня! Если понадоблюсь — просто скажите: Оливия.");
        break;
      }
      await respondTo(said);
    }
    if (state.phase !== "off") enterPassive();
  }

  // ── запуск киоска (по жесту — браузеру нужен клик для микрофона) ──
  async function startKiosk() {
    if (state.phase !== "off") return;

    try {
      const r = await fetch("/api/tts/status");
      const st = await r.json();
      state.serverTTS = !!st.available;
      console.log("[voice] server TTS:", st);
    } catch (_) { state.serverTTS = false; }

    if (SR) {
      state.inputMode = "sr";
      enterPassive();
    } else if (hasRecorder) {
      let sttOk = false;
      try {
        const st = await fetch("/api/stt/status");
        sttOk = !!(await st.json()).available;
      } catch (_) {}
      if (sttOk) {
        state.inputMode = "server";
        enterPassive();
      } else {
        enableTextMode("server STT not available");
      }
    } else {
      enableTextMode("no SR, no MediaRecorder");
    }
  }

  function stop() {
    state.phase = "off";
    setHint(false);
    disarmTapActivation();
    try { window.speechSynthesis.cancel(); } catch (_) {}
    try { state.audioEl && state.audioEl.pause(); } catch (_) {}
    try { state.rec && state.rec.stop(); } catch (_) {}
    setMode("idle");
    hudText.textContent = "IDLE";
  }

  // ── индикатор камеры (если сервер настроен с камерой) ─────
  function buildCameraBadge() {
    if (document.getElementById("cam-badge")) return;
    const el = document.createElement("div");
    el.id = "cam-badge";
    el.innerHTML = '<span id="cam-dot"></span><span id="cam-label">камера…</span>';
    document.body.appendChild(el);
    fetch("/api/camera/status")
      .then((r) => r.json())
      .then((d) => updateCameraBadge(d))
      .catch(() => {});
  }

  function updateCameraBadge(d) {
    const dot = document.getElementById("cam-dot");
    const lbl = document.getElementById("cam-label");
    if (!dot || !lbl) return;
    const badge = document.getElementById("cam-badge");
    const st = d.state || "off";
    if (st === "off") {
      badge.style.display = "none";
      return;
    }
    badge.style.display = "flex";
    const src = d.source || "";
    const shortSrc = src.includes("xiaomi") ? "Xiaomi C200"
      : src.startsWith("rtsp") ? "RTSP"
      : src.match(/^\d+$/) ? "USB-" + src : src.substring(0, 20);
    const map = {
      connecting:   { color: "#f2a13c", text: shortSrc + " — подключение…" },
      connected:    { color: "#36c79b", text: shortSrc + " — подключена" },
      reconnecting: { color: "#f2a13c", text: shortSrc + " — переподключение…" },
      error:        { color: "#ff4466", text: shortSrc + " — ошибка" },
    };
    const info = map[st] || { color: "#3a4a66", text: st };
    dot.style.background = info.color;
    dot.style.boxShadow = "0 0 8px " + info.color;
    lbl.textContent = info.text;
  }

  // SSE: статус камеры. Авто-приветствий по детекции больше НЕТ —
  // активация только по кодовому слову «Оливия».
  function connectCamera() {
    buildCameraBadge();
    const es = new EventSource("/api/events");
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d.type === "camera_status") updateCameraBadge(d);
      } catch (_) {}
    };
  }

  // ── оверлей старта (один раз, для разрешения на микрофон) ──
  function buildOverlay() {
    if (document.getElementById("start-overlay")) return;
    const hint = SR || hasRecorder
      ? "разрешите доступ к микрофону — дальше киоск работает сам"
      : "голосовой ввод недоступен — будет текстовая строка";
    const ov = document.createElement("div");
    ov.id = "start-overlay";
    ov.innerHTML =
      '<div class="ov-inner">' +
      '<div class="ov-circle"></div>' +
      '<div class="ov-title">Коснитесь экрана, чтобы включить Оливию</div>' +
      '<div class="ov-sub">администратор клиники «Стоматология №1» · ' + hint + "</div>" +
      "</div>";
    ov.addEventListener("click", () => {
      ov.classList.add("hide");
      setTimeout(() => ov.remove(), 600);
      startKiosk();
    });
    document.body.appendChild(ov);
  }

  window.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (state.phase === "active") {
      // прервать диалог → вернуться к заставке
      try { window.speechSynthesis.cancel(); } catch (_) {}
      try { state.audioEl && state.audioEl.pause(); } catch (_) {}
      try { state.rec && state.rec.stop(); } catch (_) {}
      enterPassive();
    } else {
      stop();
    }
  });

  if ("speechSynthesis" in window) {
    pickVoice();
    window.speechSynthesis.onvoiceschanged = pickVoice;
  }

  window.SmileVoice = {
    start: () => activate(""),
    startKiosk,
    stop,
    state,
  };

  // ── часы спящего режима ─────────────────────────────────
  const MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"];
  const WDAYS = ["воскресенье", "понедельник", "вторник", "среда",
    "четверг", "пятница", "суббота"];
  function tickClock() {
    const t = document.getElementById("clock-time");
    const d = document.getElementById("clock-date");
    if (!t || !d) return;
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    t.textContent = `${hh}:${mm}`;
    d.textContent = `${WDAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]}`;
  }

  function init() {
    buildOverlay();
    connectCamera();
    tickClock();
    setInterval(tickClock, 1000);
  }
  document.addEventListener("DOMContentLoaded", init);
  if (document.readyState !== "loading") init();
})();
