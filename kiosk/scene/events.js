// Случайные кинематографические события (ТЗ §19): редкие, не повторяются
// подряд, интервал 20–120 с. Устраняют ощущение зацикленности.
import * as THREE from "three";
import { PALETTE } from "./config.js";

export class CinematicDirector {
  constructor(refs, cfg) {
    this.refs = refs;        // { jellyfish, core, lightRays, background, particles, scene }
    this.cfg = cfg;
    this.timer = this._next();
    this.last = -1;
    this.active = null;
    this._tintColor = new THREE.Color();

    this.events = [
      this._foregroundPass,
      this._planktonSwarm,
      this._lightWave,
      this._strongCorePulse,
      this._rayBoost,
      this._colorShift,
    ];
  }

  _next() {
    const { intervalMin, intervalMax } = this.cfg.events;
    return intervalMin + Math.random() * (intervalMax - intervalMin);
  }

  // крупная медуза перед камерой
  _foregroundPass = () => { this.refs.jellyfish.triggerForegroundPass(); };

  // стая планктона / вспышка притяжения
  _planktonSwarm = () => {
    this._swarmT = 1.6;
  };

  // слабая волна света по фону
  _lightWave = () => {
    this._tintColor.set(PALETTE.bg[6]); // бирюзовый
    this._tint = { t: 0, dur: 4, color: this._tintColor.clone(), amt: 0.12 };
  };

  // более выраженный импульс ядра
  _strongCorePulse = () => { this.refs.core.triggerPulse(); };

  // усиление световых лучей
  _rayBoost = () => { this.refs.lightRays.boost(0.5); };

  // сцена ненадолго становится более фиолетовой/голубой
  _colorShift = () => {
    const violet = Math.random() < 0.5;
    this._tintColor.set(violet ? PALETTE.bg[5] : PALETTE.bg[6]);
    this._tint = { t: 0, dur: 8, color: this._tintColor.clone(), amt: violet ? 0.14 : 0.10 };
  };

  fire() {
    // не повторяем предыдущее событие подряд
    let idx;
    do { idx = (Math.random() * this.events.length) | 0; } while (idx === this.last && this.events.length > 1);
    this.last = idx;
    this.events[idx]();
  }

  update(dt) {
    this.timer -= dt;
    if (this.timer <= 0) { this.fire(); this.timer = this._next(); }

    // плавная отработка цветового сдвига
    if (this._tint) {
      this._tint.t += dt;
      const x = this._tint.t / this._tint.dur;
      const amt = Math.sin(Math.min(1, x) * Math.PI) * this._tint.amt;
      this.refs.background.setTint(this._tint.color, amt);
      if (x >= 1) { this.refs.background.setTint(null, 0); this._tint = null; }
    }

    // короткая вспышка притяжения планктона
    if (this._swarmT > 0) {
      this._swarmT -= dt;
      this.refs.particles.setPull(Math.max(this.refs.core.pulseEnergy, this._swarmT / 1.6 * 0.5));
    }
  }
}
