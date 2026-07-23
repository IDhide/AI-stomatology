// Энергетическое ядро Оливии (ТЗ §8) и активная сфера (§13, §16).
// В режиме ожидания — едва заметное свечение, мягко пульсирует (§8.2).
// При активации ядро «прорастает» в объёмную аудиореактивную сферу.
import * as THREE from "three";
import { SNOISE } from "./glsl.js";
import { PALETTE } from "./config.js";

const SPHERE_VERT = /* glsl */ `
  ${SNOISE}
  uniform float uTime;
  uniform float uActive;   // 0 ядро → 1 сфера
  uniform float uRms;
  uniform float uLow;
  uniform float uMid;
  varying float vDisp;
  varying vec3 vNormal;
  varying vec3 vView;

  void main(){
    vec3 n = normalize(position);
    float t = uTime * (0.25 + uMid*0.6);
    // крупная деформация от низких частот + базовое дыхание
    float big = snoise(n*1.6 + t) * (0.05 + uActive*0.03 + uLow*0.30);
    // внутренние волны от средних частот
    float mid = snoise(n*3.4 - t*1.3) * uMid * 0.14;
    float disp = big + mid;
    vDisp = disp;

    // общий размер зависит от RMS
    float scale = 1.0 + uRms * 0.20;
    vec3 pos = n * (length(position)*scale + disp);

    vNormal = normalize(normalMatrix * n);
    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    vView = -mv.xyz;
    gl_Position = projectionMatrix * mv;
  }
`;

const SPHERE_FRAG = /* glsl */ `
  precision highp float;
  uniform vec3  uCore;
  uniform vec3  uGlow;
  uniform float uActive;
  uniform float uHigh;
  uniform float uIntensity;
  varying float vDisp;
  varying vec3 vNormal;
  varying vec3 vView;

  void main(){
    vec3 V = normalize(vView);
    float fres = pow(1.0 - max(dot(V, vNormal), 0.0), 2.5);   // fresnel-кайма
    float f = smoothstep(-0.15, 0.3, vDisp);
    vec3 col = mix(uCore, uGlow, f * 0.7 + uHigh * 0.3);
    col += uGlow * fres * (0.5 + uHigh * 0.5);                 // светящаяся кайма → bloom
    col += uCore * (1.0 - fres) * 0.15;                        // внутреннее свечение
    // мягкое тонирование (Reinhard) — не даёт сфере выгореть в белый
    col = col / (1.0 + col * 0.55);
    col *= (0.6 + 0.6 * uIntensity);

    // полупрозрачная поверхность: в ядре — дымка, в активной сфере — плотнее
    float base = mix(0.06, 0.62, uActive);
    float alpha = clamp((base + fres * 0.45) * (0.5 + uIntensity * 0.6), 0.0, 0.92);
    gl_FragColor = vec4(col, alpha);
  }
`;

// Мягкая дымка/гало вокруг ядра — билборд, ребёнок ядра
const HALO_FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform vec3 uColor;
  uniform float uIntensity;
  void main(){
    float d = length(vUv - 0.5);
    float a = smoothstep(0.5, 0.0, d);
    a = pow(a, 1.6) * uIntensity;
    gl_FragColor = vec4(uColor * a, a);
  }
`;
const HALO_VERT = /* glsl */ `
  varying vec2 vUv;
  void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
`;

export class Core {
  constructor(scene, cfg) {
    this.cfg = cfg;
    this.group = new THREE.Group();
    this.group.position.set(0, -0.6, 0);
    scene.add(this.group);

    this.activation = 0;        // 0 ядро .. 1 активная сфера
    this.activationTarget = 0;
    this.intensity = cfg.core.idleIntensity;
    this.baseRadius = 1.15;

    this.audio = { rms: 0, low: 0, mid: 0, high: 0 };
    this._audioS = { rms: 0, low: 0, mid: 0, high: 0 };

    // ── сфера ──
    this.uniforms = {
      uTime: { value: 0 },
      uActive: { value: 0 },
      uRms: { value: 0 }, uLow: { value: 0 }, uMid: { value: 0 }, uHigh: { value: 0 },
      uCore: { value: new THREE.Color(PALETTE.core) },
      uGlow: { value: new THREE.Color(PALETTE.coreGlow) },
      uIntensity: { value: this.intensity },
    };
    const geo = new THREE.IcosahedronGeometry(this.baseRadius, cfg.quality === "low" ? 24 : 48);
    const mat = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      vertexShader: SPHERE_VERT,
      fragmentShader: SPHERE_FRAG,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.NormalBlending, // полупрозрачный «объём», не аддитивное выгорание
    });
    this.sphere = new THREE.Mesh(geo, mat);
    this.sphere.renderOrder = 20;
    this.group.add(this.sphere);

    // ── гало ──
    this.haloUniforms = {
      uColor: { value: new THREE.Color(PALETTE.coreGlow) },
      uIntensity: { value: 0.4 },
    };
    const halo = new THREE.Mesh(
      new THREE.PlaneGeometry(6, 6),
      new THREE.ShaderMaterial({
        uniforms: this.haloUniforms, vertexShader: HALO_VERT, fragmentShader: HALO_FRAG,
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      })
    );
    halo.renderOrder = 5;
    this.halo = halo;
    this.group.add(halo);

    // ── кольцевая волна (импульс/awakening) ──
    this.ring = this._makeRing();
    this.group.add(this.ring);
    this.ringActive = false;
    this.ringT = 0;

    // ── постоянное мягкое кольцо режима LISTENING (§14) ──
    this.listenRing = this._makeRing();
    this.listenRing.material.opacity = 0;
    this.listenRingAmt = 0;
    this.group.add(this.listenRing);

    // ── внутренние частицы сферы (§13) ──
    this.inner = this._makeInner(cfg.quality === "low" ? 60 : 140);
    this.group.add(this.inner.points);

    // idle-пульс
    this.pulseEnergy = 0;         // читают частицы/фон
    this._pulseIn = this._nextPulse();
    this._pulseT = -1;
  }

  _nextPulse() {
    const { pulseIntervalMin, pulseIntervalMax } = this.cfg.core;
    return pulseIntervalMin + Math.random() * (pulseIntervalMax - pulseIntervalMin);
  }

  _makeRing() {
    const geo = new THREE.RingGeometry(0.98, 1.02, 96);
    const mat = new THREE.MeshBasicMaterial({
      color: new THREE.Color(PALETTE.coreGlow), transparent: true, opacity: 0,
      depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    });
    const m = new THREE.Mesh(geo, mat);
    m.renderOrder = 6;
    return m;
  }

  _makeInner(n) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(n * 3);
    const rnd = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const r = Math.cbrt(Math.random()) * this.baseRadius * 0.8;
      const th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
      pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
      pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th);
      pos[i * 3 + 2] = r * Math.cos(ph);
      rnd[i] = Math.random();
    }
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aRnd", new THREE.BufferAttribute(rnd, 1));
    const uniforms = {
      uTime: { value: 0 }, uActive: { value: 0 }, uHigh: { value: 0 },
      uPixelRatio: { value: Math.min(devicePixelRatio, 2) },
      uColor: { value: new THREE.Color(0xd9c6ff) },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      vertexShader: /* glsl */ `
        ${SNOISE}
        attribute float aRnd; uniform float uTime; uniform float uPixelRatio; uniform float uActive;
        varying float vA;
        void main(){
          vec3 p = position;
          float t = uTime*0.5 + aRnd*6.28;
          p += 0.15*vec3(snoise(vec3(p.yz,t)), snoise(vec3(p.zx,t+2.0)), snoise(vec3(p.xy,t+4.0)));
          vA = (0.4 + 0.6*sin(uTime*2.0 + aRnd*30.0)) * uActive;
          vec4 mv = modelViewMatrix * vec4(p,1.0);
          gl_PointSize = (2.0 + 6.0*aRnd) * uPixelRatio * (10.0/-mv.z);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: /* glsl */ `
        uniform vec3 uColor; varying float vA;
        void main(){
          float d = length(gl_PointCoord-0.5);
          float a = smoothstep(0.5,0.0,d) * vA;
          gl_FragColor = vec4(uColor*a, a);
        }
      `,
    });
    const points = new THREE.Points(geo, mat);
    points.frustumCulled = false;
    return { points, uniforms };
  }

  get position() { return this.group.position; }

  setActivation(v) { this.activationTarget = THREE.MathUtils.clamp(v, 0, 1); }

  setAudio(a) {
    this.audio.rms = a.rms || 0;
    this.audio.low = a.low || 0;
    this.audio.mid = a.mid || 0;
    this.audio.high = a.high || 0;
  }

  // мгновенно запустить выраженный импульс (событие §19)
  triggerPulse() { this._pulseT = 0; }

  _startRing() {
    this.ringActive = true;
    this.ringT = 0;
    this.ring.material.opacity = 0.6;
    this.ring.scale.setScalar(0.6);
  }

  update(dt, t) {
    // активация (idle → сфера)
    this.activation += (this.activationTarget - this.activation) * Math.min(1, dt * 3.5);
    const act = this.activation;
    this.uniforms.uActive.value = act;
    this.inner.uniforms.uActive.value = act;

    // интенсивность: idle тускло, active ярко
    const targetInt = THREE.MathUtils.lerp(this.cfg.core.idleIntensity, this.cfg.core.activeIntensity, act);

    // idle-пульс (§8.2) только когда почти в покое
    if (act < 0.3) {
      this._pulseIn -= dt;
      if (this._pulseIn <= 0 && this._pulseT < 0) { this._pulseT = 0; this._pulseIn = this._nextPulse(); }
    }
    let pulse = 0;
    if (this._pulseT >= 0) {
      this._pulseT += dt;
      const dur = 3.2;
      const x = this._pulseT / dur;
      // мягкий рост и затухание
      pulse = Math.sin(Math.min(1, x) * Math.PI);
      if (x >= 1) this._pulseT = -1;
      if (this._pulseT >= 0 && this._pulseT < dt * 1.5) this._startRing();
    }
    this.pulseEnergy = pulse;

    // сглаживаем аудио (атака быстрая, спад плавный) — задержка < 80 мс
    for (const k of ["rms", "low", "mid", "high"]) {
      const target = this.audio[k];
      const up = target > this._audioS[k];
      const kk = up ? 0.6 : 0.12;
      this._audioS[k] += (target - this._audioS[k]) * kk;
    }
    this.uniforms.uRms.value = this._audioS.rms * act;
    this.uniforms.uLow.value = this._audioS.low * act;
    this.uniforms.uMid.value = this._audioS.mid * act;
    this.uniforms.uHigh.value = this._audioS.high * act;
    this.inner.uniforms.uHigh.value = this._audioS.high;

    // масштаб ядра: 5–12% высоты в idle, крупная сфера в active
    const idleScale = 0.32, activeScale = 1.0;
    const s = THREE.MathUtils.lerp(idleScale, activeScale, act) * (1 + pulse * 0.12 + this._audioS.rms * 0.2 * act);
    this.sphere.scale.setScalar(s);
    this.inner.points.scale.setScalar(s);

    this.intensity += (targetInt - this.intensity) * Math.min(1, dt * 3);
    this.uniforms.uIntensity.value = this.intensity + pulse * 0.25;
    this.haloUniforms.uIntensity.value = THREE.MathUtils.lerp(0.22, 0.42, act) * s + pulse * 0.22 + this._audioS.high * 0.18 * act;
    this.halo.scale.setScalar(THREE.MathUtils.lerp(1.1, 2.0, act) * (1 + pulse * 0.12));

    this.uniforms.uTime.value += dt;
    this.inner.uniforms.uTime.value += dt;

    // вращение (заметнее в thinking — задаётся извне через spin)
    this.sphere.rotation.y += dt * (0.05 + this._spin);
    this.inner.points.rotation.y += dt * (0.08 + this._spin);

    // кольцевая волна
    if (this.ringActive) {
      this.ringT += dt;
      const k = this.ringT / 1.6;
      this.ring.scale.setScalar(0.6 + k * 4.0);
      this.ring.material.opacity = Math.max(0, 0.6 * (1 - k));
      if (k >= 1) this.ringActive = false;
    }

    // постоянное кольцо LISTENING
    this.listenRingAmt += ((this._listenTarget || 0) - this.listenRingAmt) * Math.min(1, dt * 3);
    this.listenRing.material.opacity = this.listenRingAmt * (0.35 + this._audioS.rms * 0.4);
    this.listenRing.scale.setScalar(s * 1.9 + Math.sin(t * 1.5) * 0.05);

    // гало всегда лицом к камере
    this.halo.quaternion.copy(this._camQuat || this.halo.quaternion);
    if (this._camPos) {
      this.ring.lookAt(this._camPos);
      this.listenRing.lookAt(this._camPos);
    }
  }

  _spin = 0;
  setSpin(v) { this._spin = v; }
  setListenRing(v) { this._listenTarget = v; }
  faceCamera(quat, pos) { this._camQuat = quat; this._camPos = pos; }

  dispose() {
    this.sphere.geometry.dispose(); this.sphere.material.dispose();
    this.halo.geometry.dispose(); this.halo.material.dispose();
    this.ring.geometry.dispose(); this.ring.material.dispose();
    this.inner.points.geometry.dispose(); this.inner.points.material.dispose();
  }
}
