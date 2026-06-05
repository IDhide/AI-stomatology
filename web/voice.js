/* ============================================================
   voice.js — интерактивный голосовой режим Оливии в браузере
   • TTS  : window.speechSynthesis (русский голос) — Оливия говорит вслух
   • STT  : SpeechRecognition (webkit) — слушает микрофон, lang ru-RU
   • Мозг : POST /api/message → текст ответа → озвучиваем

   Цикл: приветствие → СЛУШАЮ → распознали → ДУМАЮ → /api/message →
         ГОВОРЮ → снова СЛУШАЮ. Во время речи микрофон выключен
         (чтобы Оливия не услышала саму себя).

   Браузеры требуют жест пользователя для микрофона и звука — поэтому
   стартуем по клику на оверлей «Коснитесь, чтобы поговорить».
   Работает в Chrome / Edge (webkitSpeechRecognition).
   ============================================================ */

(() => {
  "use strict";

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const hudText = document.getElementById("hud-text");

  const ui = () => window.SmileUI; // из app.js
  const setMode = (m) => ui() && ui().setMode(m);
  const setSub = (t, who) => ui() && ui().setSubtitle(t, who);

  const state = {
    active: false,
    speaking: false,
    recognizing: false,
    ruVoice: null,
    rec: null,
  };

  // ── выбор русского голоса для TTS ───────────────────────
  function pickVoice() {
    const voices = window.speechSynthesis.getVoices() || [];
    state.ruVoice =
      voices.find((v) => /ru[-_]RU/i.test(v.lang)) ||
      voices.find((v) => /^ru/i.test(v.lang)) ||
      voices.find((v) => /russian|русск/i.test(v.name)) ||
      null;
  }

  // ── произнести текст и дождаться конца ──────────────────
  function speak(text) {
    return new Promise((resolve) => {
      if (!text) return resolve();
      setMode("speaking");
      setSub(text, "bot");
      state.speaking = true;
      try { window.speechSynthesis.cancel(); } catch (_) {}

      const u = new SpeechSynthesisUtterance(text);
      u.lang = "ru-RU";
      if (state.ruVoice) u.voice = state.ruVoice;
      u.rate = 1.0;
      u.pitch = 1.05;
      u.onend = () => { state.speaking = false; resolve(); };
      u.onerror = () => { state.speaking = false; resolve(); };
      window.speechSynthesis.speak(u);

      // подстраховка: если onend не придёт (бывает в некоторых браузерах)
      const ms = Math.min(15000, 350 * text.split(/\s+/).length + 1500);
      setTimeout(() => { if (state.speaking) { state.speaking = false; resolve(); } }, ms);
    });
  }

  // ── один цикл прослушивания, возвращает распознанный текст ─
  function listenOnce() {
    return new Promise((resolve) => {
      if (!SR) return resolve("");
      setMode("listening");
      hudText.textContent = "LISTENING 🎤";

      const rec = new SR();
      state.rec = rec;
      rec.lang = "ru-RU";
      rec.interimResults = true;
      rec.maxAlternatives = 1;
      rec.continuous = false;

      let finalText = "";
      let done = false;
      const finish = (txt) => {
        if (done) return;
        done = true;
        state.recognizing = false;
        try { rec.stop(); } catch (_) {}
        resolve((txt || "").trim());
      };

      rec.onstart = () => { state.recognizing = true; };
      rec.onresult = (e) => {
        let interim = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          if (r.isFinal) finalText += r[0].transcript;
          else interim += r[0].transcript;
        }
        if (interim) setSub("вы: " + interim, "user");
        if (finalText) { setSub("вы: " + finalText, "user"); finish(finalText); }
      };
      rec.onerror = (e) => {
        // no-speech / aborted — просто завершаем пустым
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          hudText.textContent = "НЕТ ДОСТУПА К МИКРОФОНУ";
          state.active = false;
        }
        finish(finalText);
      };
      rec.onend = () => finish(finalText);

      try { rec.start(); } catch (_) { finish(""); }
    });
  }

  // ── главный диалоговый цикл ─────────────────────────────
  async function conversationLoop() {
    while (state.active) {
      const said = await listenOnce();
      if (!state.active) break;
      if (!said) {
        // тишина — слушаем снова (без спама на сервер)
        continue;
      }
      setMode("thinking");
      hudText.textContent = "THINKING…";
      let answer = "Минутку.";
      try {
        const r = await fetch("/api/message", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: said }),
        });
        const data = await r.json();
        answer = data.reply || answer;
      } catch (e) {
        answer = "Извините, связь прервалась. Повторите, пожалуйста?";
      }
      await speak(answer);
    }
    setMode("idle");
    hudText.textContent = "IDLE";
  }

  // ── запуск сессии (по жесту пользователя) ───────────────
  async function start() {
    if (state.active) return;
    if (!SR) {
      alert("Голосовой ввод поддерживается в Chrome или Edge. " +
            "Откройте демо в одном из этих браузеров.");
      return;
    }
    state.active = true;
    // «разогрев» речевого движка (нужен жест) + приветствие
    let greet = "Здравствуйте, меня зовут Оливия. Чем могу помочь?";
    try {
      const r = await fetch("/api/greeting");
      greet = (await r.json()).text || greet;
    } catch (_) {}
    await speak(greet);
    conversationLoop();
  }

  function stop() {
    state.active = false;
    try { window.speechSynthesis.cancel(); } catch (_) {}
    try { state.rec && state.rec.stop(); } catch (_) {}
    setMode("idle");
  }

  // ── оверлей «коснитесь, чтобы начать» ───────────────────
  function buildOverlay() {
    const ov = document.createElement("div");
    ov.id = "start-overlay";
    ov.innerHTML =
      '<div class="ov-inner">' +
      '<div class="ov-circle"></div>' +
      '<div class="ov-title">Коснитесь экрана, чтобы поговорить с Оливией</div>' +
      '<div class="ov-sub">администратор клиники «Стоматология №1» · разрешите доступ к микрофону</div>' +
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

  // экспорт для camera.js / отладки
  window.SmileVoice = { start, stop, state };

  // показываем оверлей (если не демо-режим сервера)
  document.addEventListener("DOMContentLoaded", buildOverlay);
  if (document.readyState !== "loading") buildOverlay();
})();
