// Частицы (ТЗ §6.4): три типа.
//  • фоновые — много, тускло, параллакс по глубине;
//  • планктон — собственное свечение, редкие вспышки, притяжение к ядру;
//  • передний план — редкие крупные размытые частицы у камеры.
import * as THREE from "three";
import { SNOISE } from "./glsl.js";

// ── круглый мягкий спрайт в фрагментном шейдере (без текстуры) ──
const SOFT = /* glsl */ `
  float soft(vec2 pc){ float d = length(pc - 0.5); return smoothstep(0.5, 0.0, d); }
`;

function makeField({ count, spread, depth, size, brightness, color }) {
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  const rnd = new Float32Array(count);       // фаза/скорость
  const sz = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    pos[i * 3] = (Math.random() - 0.5) * spread;
    pos[i * 3 + 1] = (Math.random() - 0.5) * spread * 0.7;
    pos[i * 3 + 2] = -Math.random() * depth;
    rnd[i] = Math.random();
    sz[i] = size * (0.5 + Math.random());
  }
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("aRnd", new THREE.BufferAttribute(rnd, 1));
  geo.setAttribute("aSize", new THREE.BufferAttribute(sz, 1));

  const uniforms = {
    uTime: { value: 0 },
    uBrightness: { value: brightness },
    uColor: { value: new THREE.Color(color) },
    uPixelRatio: { value: Math.min(devicePixelRatio, 2) },
    uSpread: { value: spread },
  };

  const mat = new THREE.ShaderMaterial({
    uniforms,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    fog: false, // туман имитируем вручную (depth-fade), см. ниже
    vertexShader: /* glsl */ `
      attribute float aRnd; attribute float aSize;
      uniform float uTime; uniform float uPixelRatio; uniform float uSpread;
      varying float vTw; varying float vFog;
      void main(){
        vec3 p = position;
        float t = uTime * (0.04 + aRnd*0.05);
        // медленный диагональный дрейф + мягкое покачивание
        p.y += mod(t*3.0 + aRnd*uSpread, uSpread) - uSpread*0.5;
        p.x += sin(uTime*0.15 + aRnd*20.0) * 0.25;
        // мерцание
        vTw = 0.55 + 0.45*sin(uTime*1.3 + aRnd*40.0);
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        // дальние частицы тонут в тумане (усиливает глубину, ТЗ §6.2)
        vFog = 1.0 - smoothstep(6.0, 42.0, -mv.z);
        gl_PointSize = aSize * uPixelRatio * (18.0 / -mv.z);
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */ `
      ${SOFT}
      uniform vec3 uColor; uniform float uBrightness;
      varying float vTw; varying float vFog;
      void main(){
        float a = soft(gl_PointCoord) * vTw * uBrightness * vFog;
        gl_FragColor = vec4(uColor * a, a);
      }
    `,
  });
  const points = new THREE.Points(geo, mat);
  points.frustumCulled = false;
  return { points, uniforms };
}

export class Particles {
  constructor(scene, cfg) {
    this.parts = [];

    // фоновые слои с параллаксом (несколько глубин)
    const bg = makeField({
      count: cfg.particles.count,
      spread: 34,
      depth: 40,
      size: 2.2,
      brightness: cfg.particles.brightness,
      color: 0x9fc2ff,
    });
    scene.add(bg.points);
    this.parts.push(bg);

    // крупные размытые частицы переднего плана (редкие, у камеры)
    const fg = makeField({
      count: Math.max(18, Math.round(cfg.particles.count * 0.02)),
      spread: 16,
      depth: 5,
      size: 9.0,
      brightness: cfg.particles.brightness * 0.5,
      color: 0xbcd6ff,
    });
    fg.points.position.z = 2.5; // ближе к камере
    scene.add(fg.points);
    this.parts.push(fg);

    // ── планктон: свечение + вспышки + притяжение к ядру ──
    this.plankton = this._makePlankton(cfg.particles.planktonCount);
    scene.add(this.plankton.points);
  }

  _makePlankton(count) {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(count * 3);
    const rnd = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 22;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 14;
      pos[i * 3 + 2] = -Math.random() * 16 - 1;
      rnd[i] = Math.random();
    }
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("aRnd", new THREE.BufferAttribute(rnd, 1));

    const uniforms = {
      uTime: { value: 0 },
      uPixelRatio: { value: Math.min(devicePixelRatio, 2) },
      uCore: { value: new THREE.Vector3(0, -0.4, 0) },
      uPull: { value: 0 },     // 0..1 сила притяжения к ядру
      uColor: { value: new THREE.Color(0x8fe6ff) },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      fog: false,
      vertexShader: /* glsl */ `
        ${SNOISE}
        attribute float aRnd;
        uniform float uTime; uniform float uPixelRatio;
        uniform vec3 uCore; uniform float uPull;
        varying float vFlash;
        void main(){
          vec3 p = position;
          // мягкое движение по кривым (noise)
          float t = uTime*0.12 + aRnd*10.0;
          p.x += snoise(vec3(p.yz*0.15, t)) * 0.6;
          p.y += snoise(vec3(p.xz*0.15, t+5.0)) * 0.6 + sin(t)*0.15;
          // притяжение к ядру во время импульса
          vec3 toCore = uCore - p;
          p += toCore * uPull * (0.25 + 0.35*aRnd);
          // редкие случайные вспышки
          float ph = fract(aRnd*7.0 + uTime*0.05);
          vFlash = smoothstep(0.96, 1.0, 1.0 - abs(ph-0.5)*2.0) * 3.0 + 0.4;
          vFlash += uPull * 0.6;
          vec4 mv = modelViewMatrix * vec4(p,1.0);
          gl_PointSize = (10.0 + 26.0*step(0.9, 1.0-abs(ph-0.5)*2.0)) * uPixelRatio * (14.0/-mv.z);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: /* glsl */ `
        ${SOFT}
        uniform vec3 uColor;
        varying float vFlash;
        void main(){
          float a = soft(gl_PointCoord) * vFlash;
          gl_FragColor = vec4(uColor * a, a);
        }
      `,
    });
    const points = new THREE.Points(geo, mat);
    points.frustumCulled = false;
    return { points, uniforms };
  }

  setCore(vec3) { this.plankton.uniforms.uCore.value.copy(vec3); }
  setPull(v) { this.plankton.uniforms.uPull.value = v; }
  setSpeedScale() { /* зарезервировано под изменение скорости частиц */ }

  update(dt) {
    for (const p of this.parts) p.uniforms.uTime.value += dt;
    this.plankton.uniforms.uTime.value += dt;
  }
}
