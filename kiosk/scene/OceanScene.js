// «Океан Оливии» — оркестратор сцены (ТЗ §3–§19).
// Собирает все слои, ведёт машину состояний, постобработку (bloom),
// адаптивное качество и цикл рендера. Публичный API совместим с прежним
// Visualizer: setState(), setAmplitude(); добавлены setPresence(), setAudioLevels().
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

import { Background } from "./background.js";
import { LightRays } from "./lightrays.js";
import { Particles } from "./particles.js";
import { JellyfishManager } from "./jellyfish.js";
import { Core } from "./core.js";
import { CameraRig } from "./camera.js";
import { CinematicDirector } from "./events.js";

// Целевые параметры на каждое состояние (§10–§18).
const STATE_PROFILE = {
  idle:      { activation: 0.0,  jellyDim: 1.0,  spin: 0.0,  ring: 0 },
  awakening: { activation: 1.0,  jellyDim: 0.35, spin: 0.05, ring: 0 },
  greeting:  { activation: 1.0,  jellyDim: 0.35, spin: 0.06, ring: 0 },
  listening: { activation: 0.9,  jellyDim: 0.4,  spin: 0.05, ring: 1 },
  thinking:  { activation: 0.95, jellyDim: 0.35, spin: 0.55, ring: 0 },
  speaking:  { activation: 1.0,  jellyDim: 0.35, spin: 0.1,  ring: 0 },
  goodbye:   { activation: 1.0,  jellyDim: 0.5,  spin: 0.08, ring: 0 },
  return_to_idle: { activation: 0.0, jellyDim: 1.0, spin: 0.0, ring: 0 },
};

export class OceanScene {
  constructor(canvas, cfg) {
    this.cfg = cfg;
    this.canvas = canvas;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: cfg.quality !== "low", alpha: false, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2) * cfg.render.pixelRatio);
    this.renderer.setClearColor(0x03040b, 1);
    this.renderer.autoClear = true;

    this.scene = new THREE.Scene();
    if (cfg.render.fog) this.scene.fog = new THREE.FogExp2(0x05061a, 0.055);

    this.camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.1, 200);
    this.camera.position.set(0, 0, 6.2);
    this.scene.add(this.camera); // фон/лучи — дети камеры

    // слои
    this.background = new Background(this.camera);
    this.lightRays = new LightRays(this.camera);
    this.particles = new Particles(this.scene, cfg);
    this.jellyfish = new JellyfishManager(this.scene, cfg);
    this.core = new Core(this.scene, cfg);
    this.cameraRig = new CameraRig(this.camera, cfg);
    this.director = new CinematicDirector(
      { jellyfish: this.jellyfish, core: this.core, lightRays: this.lightRays, background: this.background, particles: this.particles, scene: this.scene },
      cfg
    );

    this._initComposer();

    // машина состояний
    this.state = "idle";
    this.cur = { ...STATE_PROFILE.idle };
    this.transition = null; // {name:'awakening'|'return_to_idle', t, dur, next}
    this.present = false;

    // FPS-мониторинг для адаптивного качества (§20)
    this._frames = 0; this._fpsClock = 0; this._downgraded = false;

    this.clock = new THREE.Clock();
    this._running = true;
    this._onResize = () => this.resize();
    addEventListener("resize", this._onResize);
    this.resize();
    this._loop();
  }

  _initComposer() {
    if (!this.cfg.render.bloom) { this.composer = null; return; }
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(
      new THREE.Vector2(innerWidth, innerHeight),
      this.cfg.render.bloomStrength,
      this.cfg.render.bloomRadius,
      this.cfg.render.bloomThreshold
    );
    this.composer.addPass(this.bloom);
  }

  resize() {
    const w = innerWidth, h = innerHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.background.resize(this.camera);
    this.lightRays.resize(this.camera);
    if (this.composer) this.composer.setSize(w, h);
  }

  // ───────── публичный API ─────────
  _isReturning() { return this.state === "return_to_idle" || (this.transition && this.transition.name === "return_to_idle"); }
  _isAwakening() { return this.transition && this.transition.name === "awakening"; }

  // Присутствие человека (событие камеры). Пробуждает ядро; уход — в goodbye,
  // фактический возврат в ожидание инициирует сервер событием state:idle (§17).
  setPresence(present) {
    this.present = present;
    if (present) {
      if (this.state === "idle" || this._isReturning()) {
        this._beginTransition("awakening", this.cfg.transitions.awakeningDuration, "greeting");
      }
      this._returnAt = 0;
    } else if (this.state !== "idle" && !this._isReturning()) {
      this._setActive("goodbye");
      // страховка на случай отсутствия связи (§24): вернёмся сами через 8 с
      this._returnAt = this.clock.elapsedTime + 8;
    }
  }

  setState(state) {
    state = (state || "").toLowerCase();
    if (!STATE_PROFILE[state]) return;

    if (state === "idle") {                              // в ожидание — плавный возврат (§18)
      if (this.state !== "idle" && !this._isReturning()) {
        this._beginTransition("return_to_idle", this.cfg.transitions.returnDuration, "idle");
      }
      return;
    }
    // активное состояние
    if (this._isAwakening()) { this.transition.next = state; return; } // доиграть пробуждение
    if (this.state === "idle" || this._isReturning()) {               // бесшовно из ожидания (§12)
      this._beginTransition("awakening", this.cfg.transitions.awakeningDuration, state);
      return;
    }
    this._setActive(state);
  }

  _setActive(state) { this.transition = null; this.state = state; this._returnAt = 0; }

  // полный аудиоспектр (§16): {rms, low, mid, high}
  setAudioLevels(a) { this.core.setAudio(a); }

  // совместимость: одиночная амплитуда (пиковая) → грубые полосы
  setAmplitude(a) {
    a = Math.min(1, a || 0);
    this.core.setAudio({ rms: a, low: a * 0.9, mid: a * 0.6, high: a * 0.4 });
  }

  _beginTransition(name, dur, next) {
    this.transition = { name, t: 0, dur, next, from: { ...this.cur } };
    this.state = name;
  }

  _updateState(dt) {
    // страховка возврата в ожидание при потере связи (§24)
    if (this._returnAt && this.clock.elapsedTime > this._returnAt && !this._isReturning()) {
      this._returnAt = 0;
      this._beginTransition("return_to_idle", this.cfg.transitions.returnDuration, "idle");
    }

    // целевой профиль
    let target = STATE_PROFILE[this.state] || STATE_PROFILE.idle;

    if (this.transition) {
      const tr = this.transition;
      tr.t += dt;
      const x = Math.min(1, tr.t / tr.dur);
      const ease = x * x * (3 - 2 * x);
      const to = STATE_PROFILE[tr.name];
      // интерполируем от старого профиля к профилю перехода
      this.cur.activation = tr.from.activation + (to.activation - tr.from.activation) * ease;
      this.cur.jellyDim = tr.from.jellyDim + (to.jellyDim - tr.from.jellyDim) * ease;
      this.cur.spin = tr.from.spin + (to.spin - tr.from.spin) * ease;
      this.cur.ring = 0;
      // импульс/кольцо в начале awakening
      if (tr.name === "awakening" && tr.t < dt * 1.5) this.core.triggerPulse();
      if (x >= 1) { this.state = tr.next; this.transition = null; }
    } else {
      const k = Math.min(1, dt * 2.2);
      this.cur.activation += (target.activation - this.cur.activation) * k;
      this.cur.jellyDim += (target.jellyDim - this.cur.jellyDim) * k;
      this.cur.spin += (target.spin - this.cur.spin) * k;
      this.cur.ring = target.ring;
    }

    this.core.setActivation(this.cur.activation);
    this.core.setSpin(this.cur.spin);
    this.core.setListenRing(this.cur.ring);
    this.jellyfish.setDim(this.cur.jellyDim);
  }

  _loop() {
    if (!this._running) return;
    requestAnimationFrame(() => this._loop());
    let dt = this.clock.getDelta();
    dt = Math.min(dt, 0.05); // защита от скачков (вкладка ушла в фон)
    const t = this.clock.elapsedTime;

    this._updateState(dt);

    this.cameraRig.update(dt);
    this.background.update(dt);
    this.background.setCorePulse(this.core.pulseEnergy);
    this.lightRays.update(dt);
    this.jellyfish.update(dt, t);
    this.core.update(dt, t);
    this.core.faceCamera(this.camera.quaternion, this.camera.position);
    // частицы притягиваются к ядру во время импульса
    this.particles.setCore(this.core.position);
    this.particles.setPull(this.core.pulseEnergy * 0.5 + this.cur.activation * 0.05);
    this.particles.update(dt);
    this.director.update(dt);

    if (this.composer) this.composer.render();
    else this.renderer.render(this.scene, this.camera);

    this._monitorFps(dt);
  }

  // Если FPS устойчиво низкий — один раз снижаем нагрузку (§20/§21).
  _monitorFps(dt) {
    this._frames++; this._fpsClock += dt;
    if (this._fpsClock >= 3) {
      const fps = this._frames / this._fpsClock;
      this._frames = 0; this._fpsClock = 0;
      if (!this._downgraded && fps < 45) {
        this._downgraded = true;
        this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2) * 0.75);
        if (this.bloom) this.bloom.strength *= 0.7;
        this.resize();
        console.info(`[OceanScene] низкий FPS (${fps.toFixed(0)}) → профиль снижен`);
      }
    }
  }

  dispose() {
    this._running = false;
    removeEventListener("resize", this._onResize);
    this.jellyfish.dispose();
    this.core.dispose();
    this.renderer.dispose();
  }
}
