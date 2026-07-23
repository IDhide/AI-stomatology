// Медузы (ТЗ §7): процедурные, полупрозрачные, органичные.
// Каждая медуза уникальна (размер, форма, цвет, число и длина щупалец,
// скорость, частота пульсации). Купол деформируется vertex-шейдером
// (сокращение + волна + асимметрия), щупальца запаздывают за куполом.
import * as THREE from "three";
import { SNOISE } from "./glsl.js";
import { PALETTE } from "./config.js";

const TAU = Math.PI * 2;
const rand = (a, b) => a + Math.random() * (b - a);
const pick = (arr) => arr[(Math.random() * arr.length) | 0];

// ───────────────────────── КУПОЛ ─────────────────────────
const DOME_VERT = /* glsl */ `
  ${SNOISE}
  uniform float uTime;
  uniform float uPulse;    // 0..1 фаза сокращения
  uniform float uSeed;
  uniform float uWobble;
  varying vec3 vNormal;
  varying vec3 vPos;
  varying float vRim;      // 1 у края купола, 0 на макушке

  void main(){
    vec3 p = position;
    float top = smoothstep(-0.2, 1.0, normalize(position).y); // ~1 на макушке
    float rim = 1.0 - top;
    vRim = rim;

    // сокращение: сжатие по вертикали + расширение края (пульс)
    float contract = uPulse;
    p.y *= 1.0 - contract * 0.22 * (0.4 + top);
    p.xz *= 1.0 + contract * 0.14 * rim;

    // бегущая волна по поверхности + индивидуальная задержка участков
    float ang = atan(p.z, p.x);
    float wave = sin(ang*3.0 + uTime*2.0 + uSeed*6.28) * 0.03 * rim;
    wave += sin(ang*5.0 - uTime*1.3) * 0.015 * rim;
    p += normalize(vec3(p.x, 0.0, p.z) + 1e-4) * wave;

    // лёгкая асимметрия / «дыхание» шумом
    float n = snoise(normalize(position)*1.5 + uSeed*10.0 + uTime*0.4);
    p += normalize(position) * n * uWobble;

    vNormal = normalize(normalMatrix * normalize(position));
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vPos = mv.xyz;
    gl_Position = projectionMatrix * mv;
  }
`;

const DOME_FRAG = /* glsl */ `
  precision highp float;
  uniform vec3  uColor;
  uniform vec3  uGlow;
  uniform float uOpacity;
  uniform float uGlowIntensity;
  uniform float uDim;      // приглушение (переходы/состояния)
  varying vec3 vNormal;
  varying vec3 vPos;
  varying float vRim;

  void main(){
    vec3 V = normalize(-vPos);
    float fres = pow(1.0 - max(dot(V, vNormal), 0.0), 2.2);

    // внутреннее мягкое свечение к макушке, светящаяся окантовка по краю
    vec3 col = mix(uColor*0.4, uGlow, fres);
    col += uGlow * smoothstep(0.6, 1.0, vRim) * 0.7 * uGlowIntensity; // окантовка
    col += uColor * (1.0 - vRim) * 0.25;                              // внутренний свет

    float alpha = (0.12 + fres*0.5 + smoothstep(0.7,1.0,vRim)*0.35) * uOpacity;
    alpha *= uDim;
    col *= uDim;
    gl_FragColor = vec4(col, alpha);
  }
`;

// ─────────────────────── ЩУПАЛЬЦА ───────────────────────
// Все щупальца медузы — один LineSegments (один draw call).
// Позиция вершины считается в шейдере: висит от края купола, качается
// синусами + шумом с запаздыванием относительно пульса.
const TENT_VERT = /* glsl */ `
  ${SNOISE}
  attribute float aAngle;   // угол крепления на ободе
  attribute float aT;       // 0..1 вдоль щупальца
  attribute float aLen;     // длина
  attribute float aRadius;  // радиус крепления
  attribute float aPhase;   // индивидуальная фаза
  uniform float uTime;
  uniform float uPulse;
  uniform float uPulseLag;  // запаздывающий пульс
  uniform float uSeed;
  varying float vT;

  void main(){
    vT = aT;
    float a = aAngle;
    vec3 base = vec3(cos(a)*aRadius, 0.0, sin(a)*aRadius);

    // висят вниз; длина растягивается на сокращении (инерция)
    float len = aLen * (1.0 + uPulseLag * 0.25);
    vec3 p = base;
    p.y -= aT * len;

    // синусоидальная волна + шум, амплитуда растёт к кончику, запаздывание
    float sway = sin(uTime*1.6 + aPhase*6.28 + aT*4.0) * 0.12;
    sway += snoise(vec3(aT*2.0, uTime*0.5, aPhase*10.0)) * 0.10;
    float amp = aT*aT * len * 0.6;
    p.x += cos(a) * sway * amp + sin(uTime*0.7 + aPhase)*0.02*amp;
    p.z += sin(a) * sway * amp;
    p.x += sin(uTime*0.9 + aPhase*3.0 + aT*3.0) * 0.05 * amp;

    // импульс движения слегка «поджимает» щупальца к центру
    p.xz *= 1.0 - uPulse*0.08*aT;

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
  }
`;

const TENT_FRAG = /* glsl */ `
  precision highp float;
  uniform vec3 uColor;
  uniform float uOpacity;
  uniform float uDim;
  varying float vT;
  void main(){
    float a = (1.0 - vT) * uOpacity * uDim;   // ярче у купола, гаснет к кончику
    a *= 0.6;
    gl_FragColor = vec4(uColor * a, a);
  }
`;

class Jellyfish {
  constructor(cfg, layer) {
    this.cfg = cfg;
    this.layer = layer; // 'front' | 'mid' | 'far'
    this.group = new THREE.Group();

    const colorHex = pick(PALETTE.jelly);
    this.color = new THREE.Color(colorHex);
    this.glow = this.color.clone().lerp(new THREE.Color(0xffffff), 0.35);

    // размер зависит от плана
    const sizeByLayer = { front: rand(1.5, 2.2), mid: rand(0.9, 1.4), far: rand(0.5, 0.85) };
    this.radius = sizeByLayer[layer];

    // индивидуальные параметры
    this.seed = Math.random();
    this.pulseFreq = rand(0.35, 0.7);            // Гц-ish
    this.pulsePhase = Math.random() * TAU;
    this.wobble = rand(0.01, 0.03);
    this.speed = rand(cfg.jellyfish.minSpeed, cfg.jellyfish.maxSpeed);
    this.spin = rand(-0.15, 0.15);
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
    const seg = this.layer === "far" ? 24 : 40;
    const geo = new THREE.SphereGeometry(this.radius, seg, seg, 0, TAU, 0, Math.PI * 0.62);
    // слегка приплюснем купол
    geo.scale(1, rand(0.7, 0.95), 1);
    this.domeUniforms = {
      uTime: { value: Math.random() * 10 },
      uPulse: { value: 0 },
      uSeed: { value: this.seed },
      uWobble: { value: this.wobble },
      uColor: { value: this.color },
      uGlow: { value: this.glow },
      uOpacity: { value: rand(0.55, 0.9) },
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
      blending: THREE.NormalBlending,
    });
    this.dome = new THREE.Mesh(geo, mat);
    this.dome.renderOrder = 10;
    this.group.add(this.dome);
  }

  _buildTentacles() {
    const nMain = Math.round(rand(5, 9));
    const nThread = Math.round(rand(14, 26));
    const segs = this.cfg.jellyfish.tentacleSegments;
    const strands = [];
    const rimY = -this.radius * 0.12;

    const addStrand = (angle, radius, length, thick) => {
      strands.push({ angle, radius, length, phase: Math.random(), thick });
    };
    for (let i = 0; i < nMain; i++) {
      const a = (i / nMain) * TAU + rand(-0.1, 0.1);
      addStrand(a, this.radius * 0.72, this.radius * rand(2.4, 4.2), true);
    }
    for (let i = 0; i < nThread; i++) {
      const a = Math.random() * TAU;
      addStrand(a, this.radius * rand(0.2, 0.85), this.radius * rand(1.4, 3.0), false);
    }

    const verts = [];
    const aAngle = [], aT = [], aLen = [], aRadius = [], aPhase = [];
    for (const s of strands) {
      for (let j = 0; j < segs; j++) {
        const t0 = j / segs, t1 = (j + 1) / segs;
        // сегмент линии: две вершины
        verts.push(0, rimY, 0, 0, rimY, 0);
        aAngle.push(s.angle, s.angle);
        aT.push(t0, t1);
        aLen.push(s.length, s.length);
        aRadius.push(s.radius, s.radius);
        aPhase.push(s.phase, s.phase);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(verts, 3));
    geo.setAttribute("aAngle", new THREE.Float32BufferAttribute(aAngle, 1));
    geo.setAttribute("aT", new THREE.Float32BufferAttribute(aT, 1));
    geo.setAttribute("aLen", new THREE.Float32BufferAttribute(aLen, 1));
    geo.setAttribute("aRadius", new THREE.Float32BufferAttribute(aRadius, 1));
    geo.setAttribute("aPhase", new THREE.Float32BufferAttribute(aPhase, 1));

    this.tentUniforms = {
      uTime: { value: this.domeUniforms.uTime.value },
      uPulse: { value: 0 },
      uPulseLag: { value: 0 },
      uSeed: { value: this.seed },
      uColor: { value: this.glow },
      uOpacity: { value: rand(0.5, 0.8) },
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
    this.tentacles.position.y = -this.radius * 0.1;
    this.group.add(this.tentacles);
  }

  _zByLayer() {
    return { front: rand(1.0, 3.0), mid: rand(-3.0, -0.5), far: rand(-11, -5) }[this.layer];
  }

  _placeInitial() {
    this.group.position.set(rand(-9, 9), rand(-6, 5), this._zByLayer());
    this.vel = new THREE.Vector3(0, 0, 0);
  }

  // новая цель дрейфа — движение нелинейное, у каждой медузы свой набор
  _newTarget() {
    this.target = new THREE.Vector3(
      rand(-9, 9),
      this.group.position.y + rand(2, 7), // общий тренд — вверх
      this.group.position.z + rand(-2, 2)
    );
    this.retargetIn = rand(6, 14);
  }

  setDim(v) { this.dimTarget = v; }

  // отправить в глубину (awakening) / вернуть (return_to_idle)
  retreat(depth) { this.retreatOffset = depth; }

  update(dt, t) {
    // пульс купола (сокращение) — несимметричный цикл
    this.pulsePhase += dt * this.pulseFreq * TAU;
    const raw = Math.sin(this.pulsePhase);
    // резкое сокращение, плавное расслабление
    this.pulse = raw > 0 ? Math.pow(raw, 0.6) : raw * 0.25;
    this.pulse = Math.max(0, this.pulse);
    // запаздывающий пульс для щупалец
    this.pulseLag += (this.pulse - this.pulseLag) * Math.min(1, dt * 4);

    this.domeUniforms.uTime.value += dt;
    this.domeUniforms.uPulse.value = this.pulse;
    this.tentUniforms.uTime.value += dt;
    this.tentUniforms.uPulse.value = this.pulse;
    this.tentUniforms.uPulseLag.value = this.pulseLag;

    // приглушение
    this.dim += (this.dimTarget - this.dim) * Math.min(1, dt * 2);
    this.domeUniforms.uDim.value = this.dim;
    this.tentUniforms.uDim.value = this.dim;

    // ── движение ──
    this.retargetIn -= dt;
    if (this.retargetIn <= 0) this._newTarget();

    // импульс вверх на сокращении купола (реактивное движение)
    const propulsion = Math.max(0, this.pulse - this.pulseLag) * this.speed * 6;
    this.vel.y += propulsion * dt;

    // мягкое притяжение к цели + шумовой дрейф (нелинейность)
    const p = this.group.position;
    this.vel.x += (this.target.x - p.x) * 0.02 * dt;
    this.vel.y += (this.target.y - p.y) * 0.015 * dt;
    this.vel.z += (this.target.z - p.z) * 0.02 * dt;
    // виртуальное течение
    this.vel.x += Math.sin(t * 0.1 + this.seed * 6) * 0.03 * dt;
    this.vel.multiplyScalar(0.985);

    p.addScaledVector(this.vel, dt * 60 * this.speed * 3);
    p.y += this.speed * dt * 0.6; // фоновый подъём

    // лёгкое вращение и наклон
    this.group.rotation.y += this.spin * dt;
    this.group.rotation.z = Math.sin(t * 0.2 + this.seed * 4) * 0.08;

    // уход за границы → возврат с другой стороны/снизу (§7.1)
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
    // распределение по планам (§7.1)
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

  // событие §7.7 — крупная медуза проходит перед камерой
  triggerForegroundPass() {
    const j = this.list.find((x) => x.layer === "front") || this._spawn("front");
    j.group.position.set(rand(-6, -4) * (Math.random() < 0.5 ? 1 : -1), rand(-5, -2), rand(3, 4.5));
    j.target.set(-j.group.position.x, rand(3, 6), j.group.position.z);
    j.speed = Math.max(j.speed, this.cfg.jellyfish.maxSpeed * 0.8);
  }

  // приглушить/увести медуз в глубину (переход в активный режим §12)
  setActivePresence(active) {
    this.setDim(active ? 0.35 : 1.0);
  }

  // общий уровень приглушения всех медуз (0..1)
  setDim(v) {
    for (const j of this.list) j.setDim(v);
  }

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
