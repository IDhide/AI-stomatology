/* ============================================================
   camera.js — детекция присутствия человека через веб-камеру
   Это «железный» путь для MVP: обычная USB веб-камера → браузер.
   • getUserMedia → поток с камеры
   • покадровая разница (motion) + (если доступно) FaceDetector API
   • при устойчивом обнаружении → POST /api/trigger (как «лицо найдено»)
   • при уходе человека сервер сам возвращает киоск в idle

   Включается флагом в URL:  http://<host>:8080/?camera=1
   Без флага киоск работает в режиме авто-сценария/ручного триггера.
   ============================================================ */

(() => {
  "use strict";

  const params = new URLSearchParams(location.search);
  if (params.get("camera") !== "1") return; // камера off по умолчанию

  const PRESENCE_FRAMES = 4;     // сколько кадров подряд «есть человек» до триггера
  const ABSENCE_FRAMES = 25;     // кадров «пусто» до сброса
  const MOTION_THRESHOLD = 0.012; // доля изменившихся пикселей
  const SAMPLE_W = 64, SAMPLE_H = 48;
  const INTERVAL_MS = 150;

  const log = (...a) => console.log("[camera]", ...a);

  // маленький self-view в углу
  const video = document.createElement("video");
  video.autoplay = true; video.muted = true; video.playsInline = true;
  Object.assign(video.style, {
    position: "fixed", right: "14px", bottom: "14px", width: "160px",
    borderRadius: "10px", opacity: "0.85", zIndex: 50,
    boxShadow: "0 0 0 1px rgba(255,255,255,0.12)",
  });
  const badge = document.createElement("div");
  Object.assign(badge.style, {
    position: "fixed", right: "14px", bottom: "128px", zIndex: 51,
    font: "12px Inter, sans-serif", letterSpacing: "0.1em",
    color: "#9fe1cb", textTransform: "uppercase",
  });
  badge.textContent = "камера…";

  const buf = document.createElement("canvas");
  buf.width = SAMPLE_W; buf.height = SAMPLE_H;
  const bctx = buf.getContext("2d", { willReadFrequently: true });

  let prev = null;
  let present = 0, absent = 0, active = false;
  let faceDetector = null;

  async function start() {
    document.body.appendChild(video);
    document.body.appendChild(badge);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 }, audio: false,
      });
      video.srcObject = stream;
      log("камера подключена:", stream.getVideoTracks()[0]?.label || "unknown");
      badge.textContent = "● камера активна";
    } catch (e) {
      log("нет доступа к камере:", e.message);
      badge.textContent = "камера недоступна";
      return;
    }

    if ("FaceDetector" in window) {
      try { faceDetector = new window.FaceDetector({ fastMode: true }); }
      catch (_) {}
    }
    setInterval(tick, INTERVAL_MS);
  }

  async function tick() {
    if (video.readyState < 2) return;

    let humanLikely = false;

    // 1) детекция лица (если браузер поддерживает)
    if (faceDetector) {
      try {
        const faces = await faceDetector.detect(video);
        if (faces && faces.length) humanLikely = true;
      } catch (_) {}
    }

    // 2) детекция движения (всегда) — кадровая разница на даунскейле
    bctx.drawImage(video, 0, 0, SAMPLE_W, SAMPLE_H);
    const cur = bctx.getImageData(0, 0, SAMPLE_W, SAMPLE_H).data;
    if (prev) {
      let changed = 0;
      for (let i = 0; i < cur.length; i += 4) {
        const d =
          Math.abs(cur[i] - prev[i]) +
          Math.abs(cur[i + 1] - prev[i + 1]) +
          Math.abs(cur[i + 2] - prev[i + 2]);
        if (d > 60) changed++;
      }
      const ratio = changed / (SAMPLE_W * SAMPLE_H);
      if (ratio > MOTION_THRESHOLD) humanLikely = true;
    }
    prev = cur.slice(0);

    // 3) машина состояний присутствия
    if (humanLikely) { present++; absent = 0; }
    else { absent++; present = Math.max(0, present - 1); }

    if (!active && present >= PRESENCE_FRAMES) {
      active = true;
      badge.textContent = "● человек обнаружен";
      log("человек обнаружен");
      // в интерактивном режиме — запускаем голосовую сессию Оливии,
      // иначе (демо-сценарий) — дёргаем серверный триггер
      if (window.SmileVoice && !window.SmileVoice.state.active) {
        window.SmileVoice.start();
      } else if (!window.SmileVoice) {
        fetch("/api/trigger", { method: "POST" }).catch(() => {});
      }
    } else if (active && absent >= ABSENCE_FRAMES) {
      active = false;
      badge.textContent = "● камера активна";
      log("человек ушёл");
    }
  }

  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    start();
  } else {
    log("getUserMedia не поддерживается этим браузером");
  }
})();
