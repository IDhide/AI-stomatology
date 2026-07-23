// Медузы (ТЗ §7): процедурные, полупрозрачные, реалистичные.
// Купол — тонкий «стеклянный» биолюминесцентный колокол с радиальными
// каналами, светящейся зубчатой каймой и внутренним ядром; деформируется
// vertex-шейдером (сокращение + флип края + волна + асимметрия).
// Щупальца — струящиеся дуги с бегущими волнами и запаздыванием, плюс
// несколько более ярких ротовых лопастей у центра.
import * as THREE from "three";
import { SNOISE } from "./glsl.js";
import { PALETTE } from "./config.js";

const TAU = Math.PI * 2;
const rand = (a, b) => a + Math.random() * (b - a);
const irand = (a, b) => Math.round(rand(a, b));
const pick = (arr) => arr[(Math.random() * arr.length) | 0];

// ───────────────────────── КОЛОКОЛ ─────────────────────────
const DOME_VERT = /* glsl */ `
  ${SNOISE}
  uniform float uTime;
  uniform float uPulse;    // 0..1 фаза сокращения (реактивный толчок)
  uniform float uSeed;
  uniform float uWobble;
  uniform float uLobes;    // число долей края колокола
  varying vec3 vNormal;
  varying vec3 vView;
  varying float vRim;      // 0 на макушке → 1 у кромки
  varying float vTop;
  varying float vAng;      // азимут

  void main(){
    vec3 nrm = normalize(position);
    float top = smoothstep(-0.1, 1.0, nrm.y);   // ~1 на макушке
    float rim = 1.0 - top;
    float ang = atan(position.z, position.x);
    vRim = rim; vTop = top; vAng = ang;

    vec3 p = position;

    // зубчатость края (доли колокола) — реалистичный волнистый край
    float lobe = cos(ang * uLobes) * rim * rim * 0.06;
    p.xz *= 1.0 + lobe;

    // сокращение: сжатие по вертикали + подгиб кромки внутрь-вверх (закрытие)
    float c = uPulse;
    p.y  *= 1.0 - c * 0.16 * (0.3 + top);
    p.xz *= 1.0 + c * 0.16 * rim * rim;
    p.y  += c * 0.14 * rim * rim;

    // бегущая волна по поверхности
    float wave = sin(ang*3.0 + uTime*2.0 + uSeed*6.28) * 0.022 * rim;
    wave += sin(ang*6.0 - uTime*1.4) * 0.010 * rim;
    p += normalize(vec3(position.x, 0.0, position.z) + 1e-4) * wave;

    // лёгкое «дыхание»/асимметрия шумом
    p += nrm * snoise(nrm*1.4 + uSeed*10.0 + uTime*0.3) * uWobble;

    vNormal = normalize(normalMatrix * nrm);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vView = -mv.xyz;
    gl_Position = projectionMatrix * mv;
  }
`;

const DOME_FRAG = /* glsl */ `
  precision highp float;
  uniform vec3  uColor;
  uniform vec3  uGlow;
  uniform float uGlowIntensity;
  uniform float uDim;
  uniform float uCanals;   // число радиальных каналов
  varying vec3 vNormal;
  varying vec3 vView;
  varying float vRim;
  varying float vTop;
  varying float vAng;

  void main(){
    vec3 V = normalize(vView);
    float fres = pow(1.0 - max(dot(V, vNormal), 0.0), 2.0);  // стеклянная кайма

    // радиальные гастральные каналы — тонкие светлые линии от центра к краю
    float canals = pow(abs(sin(vAng * uCanals)), 10.0);
    canals *= smoothstep(0.08, 0.75, vRim);

    // внутреннее ядро (манубриум/гонады) — мягкое свечение у макушки
    float nucleus = smoothstep(0.5, 1.0, vTop);

    // яркая светящаяся кромка колокола
    float lip = smoothstep(0.80, 1.0, vRim);

    vec3 col = uColor * 0.26;
    col += uGlow * fres * 0.60;                        // прозрачный светящийся край
    col += uColor * canals * 0.38;                    // каналы
    col += uGlow * lip * (0.55 + uGlowIntensity*0.6); // кромка → bloom
    col += uGlow * nucleus * 0.28;                    // внутреннее свечение

    // дальняя стенка колокола — тусклее, чтобы «экватор» не выгорал в белый
    float face = gl_FrontFacing ? 1.0 : 0.4;
    col *= uDim * face;
    col = col / (1.0 + col * 0.85);                    // тонирование, без выгорания

    // прозрачность: тело почти стекло, ярче у края/кромки/каналов
    float alpha = (0.05 + fres * 0.28 + lip * 0.34 + canals * 0.12) * uDim * face;
    gl_FragColor = vec4(col, alpha);
  }
`;

// ─────────────────────── ЩУПАЛЬЦА / ЛОПАСТИ ───────────────────────
const TENT_VERT = /* glsl */ `
  ${SNOISE}
  attribute float aAngle;   // азимут крепления
  attribute float aT;       // 0..1 вдоль
  attribute float aLen;     // длина
  attribute float aRadius;  // радиус крепления на кромке
  attribute float aPhase;   // индивидуальная фаза
  attribute float aCurl;    // базовая кривизна (дуга)
  attribute float aFreq;    // частота колебаний
  attribute float aOpacity; // яркость конкретной пряди
  uniform float uTime;
  uniform float uPulse;
  uniform float uPulseLag;
  varying float vT;
  varying float vOpacity;

  void main(){
    vT = aT; vOpacity = aOpacity;
    float a = aAngle;
    vec3 base = vec3(cos(a)*aRadius, 0.0, sin(a)*aRadius);

    float len = aLen * (1.0 + uPulseLag * 0.20);
    float t = aT;

    vec3 p = base;
    p.y -= t * len;                                   // висит вниз

    // струящаяся дуга: плавный увод в сторону, растёт к кончику
    float arc = t * t * aCurl;
    // бегущая волна (синус + шум) с запаздыванием и разной скоростью
    float w = sin(uTime*aFreq + aPhase*6.28 + t*5.0);
    w += snoise(vec3(t*2.5, uTime*0.4, aPhase*10.0)) * 0.6;
    float amp = t * t * len * 0.42;

    // отклонение в касательном и радиальном направлениях (объёмный изгиб)
    vec2 tangent = vec2(-sin(a), cos(a));
    vec2 radial  = vec2(cos(a), sin(a));
    vec2 off = tangent * (w * amp) + radial * (arc + w * amp * 0.4);
    p.x += off.x;
    p.z += off.y;
    p.x += sin(uTime*0.7 + aPhase*3.0 + t*3.0) * 0.03 * amp;

    // толчок колокола слегка поджимает щупальца к оси
    p.xz *= 1.0 - uPulse * 0.06 * t;

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
  }
`;

const TENT_FRAG = /* glsl */ `
  precision highp float;
  uniform vec3 uColor;
  uniform float uDim;
  varying float vT;
  varying float vOpacity;
  void main(){
    // ярче у купола, мягко гаснет к кончику
    float a = pow(1.0 - vT, 1.3) * vOpacity * uDim;
    gl_FragColor = vec4(uColor * a, a);
  }
`;

class Jellyfish {
  constructor(cfg, layer) {
    this.cfg = cfg;
    this.layer = layer;
    this.group = new THREE.Group();

    const colorHex = pick(PALETTE.jelly);
    this.color = new THREE.Color(colorHex);
    this.glow = this.color.clone().lerp(new THREE.Color(0xffffff), 0.22);

    const sizeByLayer = { front: rand(1.5, 2.2), mid: rand(0.9, 1.4), far: rand(0.5, 0.85) };
    this.radius = sizeByLayer[layer];

    this.seed = Math.random();
    this.lobes = irand(6, 12);
    this.canals = irand(7, 14);
    this.pulseFreq = rand(0.32, 0.62);
    this.pulsePhase = Math.random() * TAU;
    this.wobble = rand(0.008, 0.022);
    this.speed = rand(cfg.jellyfish.minSpeed, cfg.jellyfish.maxSpeed);
    this.spin = rand(-0.12, 0.12);
    this.pulse = 0;
    this.pulseLag = 0;
    this.dim = 1;
    this.dimTarget = 1;

    this._buildDome();
    this._buildTentacles();
    this._placeInitial();
    this._newTarget();
  }

  _buildDome() {
    const seg = this.layer === "far" ? 32 : 56;
    // тонкий вытянутый колокол (не плоская «шляпка»)
    const geo = new THREE.SphereGeometry(this.radius, seg, seg, 0, TAU, 0, Math.PI * 0.66);
    geo.scale(1, rand(0.72, 1.02), 1);

    this.domeUniforms = {
      uTime: { value: Math.random() * 10 },
      uPulse: { value: 0 },
      uSeed: { value: this.seed },
      uWobble: { value: this.wobble },
      uLobes: { value: this.lobes },
      uCanals: { value: this.canals },
      uColor: { value: this.color },
      uGlow: { value: this.glow },
      uGlowIntensity: { value: this.cfg.jellyfish.glowIntensity },
      uDim: { value: 1 },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms: this.domeUniforms,
      vertexShader: DOME_VERT,
      fragmentShader: DOME_FRAG,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending, // биолюминесцентное свечение + тонирование в шейдере
    });
    this.dome = new THREE.Mesh(geo, mat);
    this.dome.renderOrder = 10;
    this.group.add(this.dome);
  }

  _buildTentacles() {
    const segs = this.cfg.jellyfish.tentacleSegments;
    const strands = [];
    const rimR = this.radius * 0.86;

    // краевые нити — много, тонкие, длинные, струящиеся
    const nThread = irand(22, 40);
    for (let i = 0; i < nThread; i++) {
      const a = (i / nThread) * TAU + rand(-0.06, 0.06);
      strands.push({
        angle: a,
        radius: rimR * rand(0.9, 1.0),
        length: this.radius * rand(2.6, 4.6),
        phase: Math.random(),
        curl: rand(-0.5, 0.5) * this.radius,
        freq: rand(1.1, 1.8),
        opacity: rand(0.28, 0.5),
      });
    }
    // основные щупальца — заметнее, чуть толще (пучок из 2 линий)
    const nMain = irand(5, 8);
    for (let i = 0; i < nMain; i++) {
      const a = (i / nMain) * TAU + rand(-0.12, 0.12);
      const curl = rand(-0.35, 0.35) * this.radius;
      const len = this.radius * rand(3.2, 5.4);
      for (let k = 0; k < 2; k++) {
        strands.push({
          angle: a + (k - 0.5) * 0.05,
          radius: rimR * 0.8,
          length: len,
          phase: Math.random(),
          curl,
          freq: rand(0.9, 1.4),
          opacity: rand(0.5, 0.72),
        });
      }
    }
    // ротовые лопасти — короче, у центра, ярче, более «фриллистые»
    const nOral = irand(4, 6);
    for (let i = 0; i < nOral; i++) {
      const a = (i / nOral) * TAU + rand(-0.1, 0.1);
      strands.push({
        angle: a,
        radius: this.radius * rand(0.12, 0.28),
        length: this.radius * rand(1.8, 3.0),
        phase: Math.random(),
        curl: rand(-0.6, 0.6) * this.radius,
        freq: rand(1.4, 2.2),
        opacity: rand(0.55, 0.8),
      });
    }

    const verts = [];
    const A = { aAngle: [], aT: [], aLen: [], aRadius: [], aPhase: [], aCurl: [], aFreq: [], aOpacity: [] };
    const push = (s, t) => {
      verts.push(0, 0, 0);
      A.aAngle.push(s.angle); A.aT.push(t); A.aLen.push(s.length);
      A.aRadius.push(s.radius); A.aPhase.push(s.phase);
      A.aCurl.push(s.curl); A.aFreq.push(s.freq); A.aOpacity.push(s.opacity);
    };
    for (const s of strands) {
      for (let j = 0; j < segs; j++) { push(s, j / segs); push(s, (j + 1) / segs); }
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
    for (const key of Object.keys(A)) {
      geo.setAttribute(key, new THREE.Float32BufferAttribute(A[key], 1));
    }

    // opacity через атрибут: одна медуза = один draw call, но с разной яркостью
    this.tentUniforms = {
      uTime: { value: this.domeUniforms.uTime.value },
      uPulse: { value: 0 },
      uPulseLag: { value: 0 },
      uColor: { value: this.glow },
      uDim: { value: 1 },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms: this.tentUniforms,
      vertexShader: TENT_VERT,
      fragmentShader: TENT_FRAG,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    this.tentacles = new THREE.LineSegments(geo, mat);
    this.tentacles.renderOrder = 9;
    this.tentacles.position.y = -this.radius * 0.06;
    this.group.add(this.tentacles);
  }

  _zByLayer() {
    return { front: rand(1.0, 3.0), mid: rand(-3.0, -0.5), far: rand(-11, -5) }[this.layer];
  }

  _placeInitial() {
    this.group.position.set(rand(-9, 9), rand(-6, 5), this._zByLayer());
    this.vel = new THREE.Vector3(0, 0, 0);
  }

  _newTarget() {
    this.target = new THREE.Vector3(
      rand(-9, 9),
      this.group.position.y + rand(2, 7),
      this.group.position.z + rand(-2, 2)
    );
    this.retargetIn = rand(6, 14);
  }

  setDim(v) { this.dimTarget = v; }

  update(dt, t) {
    // пульс купола — резкое сокращение, плавное расслабление
    this.pulsePhase += dt * this.pulseFreq * TAU;
    const raw = Math.sin(this.pulsePhase);
    this.pulse = Math.max(0, raw > 0 ? Math.pow(raw, 0.6) : raw * 0.25);
    this.pulseLag += (this.pulse - this.pulseLag) * Math.min(1, dt * 4);

    this.domeUniforms.uTime.value += dt;
    this.domeUniforms.uPulse.value = this.pulse;
    this.tentUniforms.uTime.value += dt;
    this.tentUniforms.uPulse.value = this.pulse;
    this.tentUniforms.uPulseLag.value = this.pulseLag;

    this.dim += (this.dimTarget - this.dim) * Math.min(1, dt * 2);
    this.domeUniforms.uDim.value = this.dim;
    this.tentUniforms.uDim.value = this.dim;

    // ── движение ──
    this.retargetIn -= dt;
    if (this.retargetIn <= 0) this._newTarget();

    const propulsion = Math.max(0, this.pulse - this.pulseLag) * this.speed * 6;
    this.vel.y += propulsion * dt;

    const p = this.group.position;
    this.vel.x += (this.target.x - p.x) * 0.02 * dt;
    this.vel.y += (this.target.y - p.y) * 0.015 * dt;
    this.vel.z += (this.target.z - p.z) * 0.02 * dt;
    this.vel.x += Math.sin(t * 0.1 + this.seed * 6) * 0.03 * dt;
    this.vel.multiplyScalar(0.985);

    p.addScaledVector(this.vel, dt * 60 * this.speed * 3);
    p.y += this.speed * dt * 0.6;

    this.group.rotation.y += this.spin * dt;
    this.group.rotation.z = Math.sin(t * 0.2 + this.seed * 4) * 0.07;

    if (p.y > 9) { p.y = -9; p.x = rand(-9, 9); this._newTarget(); }
    if (p.x > 12) p.x = -12; else if (p.x < -12) p.x = 12;
  }

  dispose() {
    this.dome.geometry.dispose();
    this.dome.material.dispose();
    this.tentacles.geometry.dispose();
    this.tentacles.material.dispose();
  }
}

export class JellyfishManager {
  constructor(scene, cfg) {
    this.scene = scene;
    this.cfg = cfg;
    this.list = [];
    this.foregroundTimer = rand(30, 90);

    const count = Math.round(rand(cfg.jellyfish.minCount, cfg.jellyfish.maxCount));
    const layers = [];
    layers.push("front");
    for (let i = 0; i < Math.ceil(count * 0.4); i++) layers.push("mid");
    while (layers.length < count) layers.push("far");
    for (const l of layers) this._spawn(l);
  }

  _spawn(layer) {
    const j = new Jellyfish(this.cfg, layer);
    this.scene.add(j.group);
    this.list.push(j);
    return j;
  }

  triggerForegroundPass() {
    const j = this.list.find((x) => x.layer === "front") || this._spawn("front");
    j.group.position.set(rand(-6, -4) * (Math.random() < 0.5 ? 1 : -1), rand(-5, -2), rand(3, 4.5));
    j.target.set(-j.group.position.x, rand(3, 6), j.group.position.z);
    j.speed = Math.max(j.speed, this.cfg.jellyfish.maxSpeed * 0.8);
  }

  setActivePresence(active) { this.setDim(active ? 0.35 : 1.0); }

  setDim(v) { for (const j of this.list) j.setDim(v); }

  update(dt, t) {
    for (const j of this.list) j.update(dt, t);
    this.foregroundTimer -= dt;
    if (this.foregroundTimer <= 0) {
      this.triggerForegroundPass();
      this.foregroundTimer = rand(30, 90);
    }
  }

  dispose() {
    for (const j of this.list) { this.scene.remove(j.group); j.dispose(); }
    this.list = [];
  }
}
