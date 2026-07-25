// Визуализатор «fluid nebula» — тёмное ядро-сфера, органическое светящееся
// облако вокруг с плотными концентрическими рябью-волнами, эквалайзер,
// неоновая палитра: electric blue → violet → magenta. Всё — полноэкранный
// фрагментный шейдер на Three.js; JS-класс не изменён.
import * as THREE from "three";

const VERT = /* glsl */ `
  void main() { gl_Position = vec4(position, 1.0); }
`;

const FRAG = /* glsl */ `
  precision highp float;
  uniform vec2  uRes;
  uniform float uTime;
  uniform float uAmp;
  uniform float uActivity;
  uniform float uBands[8];

  // ── simplex 2D (Ashima) ────────────────────────────────────────
  vec3 mod289(vec3 x){ return x - floor(x * (1.0/289.0)) * 289.0; }
  vec2 mod289(vec2 x){ return x - floor(x * (1.0/289.0)) * 289.0; }
  vec3 permute(vec3 x){ return mod289(((x*34.0)+1.0)*x); }

  float snoise(vec2 v){
    const vec4 C = vec4(0.211324865405187, 0.366025403784439,
                       -0.577350269189626, 0.024390243902439);
    vec2 i  = floor(v + dot(v, C.yy));
    vec2 x0 = v - i + dot(i, C.xx);
    vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;
    i = mod289(i);
    vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0))
                            + i.x + vec3(0.0, i1.x, 1.0));
    vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy),
                             dot(x12.zw,x12.zw)), 0.0);
    m = m*m; m = m*m;
    vec3 x = 2.0 * fract(p * C.www) - 1.0;
    vec3 h = abs(x) - 0.5;
    vec3 ox = floor(x + 0.5);
    vec3 a0 = x - ox;
    m *= 1.79284291400159 - 0.85373472095314 * (a0*a0 + h*h);
    vec3 g;
    g.x = a0.x * x0.x + h.x * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;
    return 130.0 * dot(m, g);
  }

  float fbm(vec2 p){
    float v = 0.0, a = 0.5;
    vec2 shift = vec2(100.0);
    mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
    for (int i = 0; i < 6; i++){
      v += a * snoise(p);
      p = rot * p * 2.02 + shift;
      a *= 0.48;
    }
    return v;
  }

  void main(){
    vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / min(uRes.x, uRes.y);
    float r = length(uv);
    vec2 dir = uv / max(r, 1e-5);
    float t = uTime;

    // ── эквалайзер по секторам ────────────────────────────────────
    float a01 = atan(uv.y, uv.x) / 6.2831853 + 0.5;
    float bp = a01 * 8.0;
    float band = 0.0;
    for (int i = 0; i < 8; i++){
      float fi = float(i);
      float w = max(0.0, 1.0 - abs(bp - fi));
      w = max(w, max(0.0, 1.0 - abs(bp - fi - 8.0)));
      w = max(w, max(0.0, 1.0 - abs(bp - fi + 8.0)));
      band += uBands[i] * w;
    }

    // ── ядро-сфера (тёмная void) ─────────────────────────────────
    float sr = 0.180 + uAmp * 0.014 + uActivity * 0.005;
    float sd = r - sr;
    float sphereMask = smoothstep(0.006, -0.006, sd);

    // ── органическая деформация внешнего контура (fluid blob) ──────
    float distortAmp = 0.025 + uAmp * 0.06 + uActivity * 0.02;
    float warp1 = fbm(dir * 2.5 + vec2(t * 0.12, 3.7)) * distortAmp;
    float warp2 = snoise(dir * 4.0 + vec2(-t * 0.08, 7.0)) * distortAmp * 0.5;
    float outerBlob = sr + 0.09 + warp1 + warp2 + band * 0.025;
    float d = r - outerBlob;

    // ── плотные концентрические волны (3 слоя, чистые кольца) ─────
    float waveZone = exp(-max(d, 0.0) * 5.0);
    float speed = 1.6 + uAmp * 5.0;
    float wAmpTotal = 0.04 + uActivity * 0.03 + band * 0.50 + uAmp * 0.12;

    // Лёгкая органика: небольшое радиальное смещение через шум,
    // НО без углового искажения — кольца остаются круглыми.
    float radialWarp = (snoise(dir * 1.8 + vec2(t * 0.07, 2.0)) - 0.5) * 0.006;

    // слой 1 — мелкая рябь (высокая частота)
    float ph1 = (r + radialWarp) * 180.0 - t * speed * 2.2;
    float w1 = smoothstep(0.3, 0.5, 0.5 + 0.5 * sin(ph1)) * 0.35;

    // слой 2 — средние волны
    float ph2 = (r + radialWarp * 1.3) * 110.0 - t * speed * 1.5;
    float w2 = smoothstep(0.35, 0.5, 0.5 + 0.5 * sin(ph2)) * 0.45;

    // слой 3 — широкие гребни
    float ph3 = (r + radialWarp * 0.7) * 65.0 - t * speed * 0.9;
    float w3 = smoothstep(0.4, 0.5, 0.5 + 0.5 * sin(ph3)) * 0.25;

    float waves = (w1 + w2 + w3) * wAmpTotal;

    // ── профиль свечения: кольцо + ореол + внутренний край ─────────
    float ring  = exp(-d * d / 0.012);
    float halo  = exp(-max(d, 0.0) * 3.8) * 0.55;
    float inner = exp(-max(-d, 0.0) * 9.0) * 0.45;
    float core  = smoothstep(0.0, sr * 0.85, r);

    float litBase = ring * 0.85 + halo + inner;
    litBase *= (1.0 - waves * wAmpTotal * 2.5);
    litBase *= mix(0.06, 1.0, core);

    // ── 3D-освещение кольца: свет снизу-слева, тень сверху ────────
    float lightKey = dot(dir, normalize(vec2(-0.50, -0.65)));
    float lightFill = dot(dir, normalize(vec2(0.60, 0.20)));
    litBase *= 0.55 + 0.45 * smoothstep(-0.3, 0.9, lightKey);

    // ── палитра: electric blue → violet → neon magenta ─────────────
    float hueA = fbm(dir * 1.4 + vec2(17.0, t * 0.055));
    float hueB = fbm(dir * 1.1 + vec2(-7.0, t * 0.040));
    float hueC = fbm(dir * 0.8 + vec2(22.0, t * 0.030));

    vec3 deepBlue    = vec3(0.05, 0.10, 0.50);
    vec3 electricBlue= vec3(0.15, 0.30, 0.95);
    vec3 violet      = vec3(0.46, 0.20, 0.96);
    vec3 neonMagenta = vec3(0.95, 0.15, 0.85);
    vec3 neonPink    = vec3(1.00, 0.30, 0.70);

    vec3 col = mix(deepBlue, electricBlue, smoothstep(0.0, 0.45, hueA));
    col = mix(col, violet, smoothstep(0.30, 0.65, hueB) * 0.85);
    col = mix(col, neonMagenta, smoothstep(0.55, 0.82, hueC) * 0.80);
    col = mix(col, neonPink, smoothstep(0.80, 0.97, hueA) * 0.50);

    // ── фон ───────────────────────────────────────────────────────
    vec3 bg = mix(vec3(0.025, 0.015, 0.080), vec3(0.008, 0.004, 0.025),
                  smoothstep(0.0, 1.2, r));
    bg += vec3(0.06, 0.04, 0.18) * exp(-r * 3.5)
        * (0.30 + 0.25 * lightFill) * (1.0 - core);

    vec3 final_col = bg + col * litBase * (0.50 + uAmp * 0.60);

    // ── bloom: мягкое свечение вокруг активной зоны ────────────────
    float bloom = exp(-max(d, 0.0) * 2.2) * 0.35;
    float bloomOuter = exp(-max(d - 0.04, 0.0) * 3.5) * 0.18;
    vec3 bloomCol = mix(violet, neonMagenta, 0.5 + 0.3 * sin(t * 0.4));
    final_col += bloomCol * (bloom + bloomOuter) * (0.4 + uAmp * 0.5);

    // виньетирование
    final_col *= 1.0 - 0.50 * smoothstep(0.50, 1.30, r);

    // ── 3D-сфера-ядро ────────────────────────────────────────────
    float nz = sqrt(max(1.0 - (r * r) / (sr * sr), 0.0));
    vec3 N = vec3(uv / sr, nz);

    float bump = (snoise(uv * 8.0 + vec2(t * 0.3, -t * 0.2)) - 0.5)
               * (0.12 + uAmp * 0.5);
    N = normalize(N + vec3(bump * 0.20));

    vec3 L = normalize(vec3(-0.35, 0.65, 0.60));
    float diff = clamp(dot(N, L), 0.0, 1.0);

    vec3 sBase = vec3(0.04, 0.02, 0.10);
    vec3 sMid  = vec3(0.22, 0.12, 0.55);
    vec3 sHi   = vec3(0.70, 0.55, 1.00);

    vec3 sc = mix(sBase, sMid, smoothstep(0.0, 0.80, diff));
    sc = mix(sc, sHi, pow(diff, 5.0) * 0.80);

    // ── неоновый магента-блик снизу-слева ─────────────────────────
    vec3 Lspec = normalize(vec3(-0.55, -0.70, 0.75));
    vec3 V = vec3(0.0, 0.0, 1.0);
    vec3 H = normalize(Lspec + V);
    float spec = pow(max(0.0, dot(N, H)), 24.0);
    sc += neonMagenta * spec * 0.90;

    // ── мягкий синий ambient справа ────────────────────────────────
    float ambient = max(0.0, dot(N, normalize(vec3(0.70, 0.15, 0.50))));
    sc += electricBlue * ambient * 0.18;

    // rim light — светящаяся кромка
    float rim = pow(1.0 - nz, 3.0);
    sc += mix(neonMagenta, violet, 0.5) * rim * 0.50;

    sc *= 1.0 + uAmp * 0.40;
    sc *= 0.96 + 0.07 * snoise(uv * 6.0 + t * 0.12);

    final_col = mix(final_col, sc, sphereMask);

    // свечение у кромки шара
    final_col += mix(violet, neonMagenta, 0.6)
               * exp(-max(sd, 0.0) * 30.0) * (0.18 + uAmp * 0.28)
               * (1.0 - sphereMask);

    gl_FragColor = vec4(final_col, 1.0);
  }
`;

export class Visualizer {
  constructor(canvas) {
    this.canvas = canvas;
    this.amp = 0;
    this.ampTarget = 0;
    this.activity = 0.15;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

    this.scene = new THREE.Scene();
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

    this.bands = new Float32Array(8);        // сглаженные значения
    this.bandTargets = new Float32Array(8);  // свежие с плеера

    this.uniforms = {
      uRes: { value: new THREE.Vector2(1, 1) },
      uTime: { value: 0 },
      uAmp: { value: 0 },
      uActivity: { value: 0.15 },
      uBands: { value: this.bands },
    };

    const quad = new THREE.Mesh(
      new THREE.PlaneGeometry(2, 2),
      new THREE.ShaderMaterial({
        uniforms: this.uniforms,
        vertexShader: VERT,
        fragmentShader: FRAG,
      }),
    );
    this.scene.add(quad);

    this.resize();
    addEventListener("resize", () => this.resize());
    this.clock = new THREE.Clock();
    this._loop();
  }

  resize() {
    const w = innerWidth, h = innerHeight;
    this.renderer.setSize(w, h, false);
    const pr = this.renderer.getPixelRatio();
    this.uniforms.uRes.value.set(w * pr, h * pr);
  }

  // 0..1 — амплитуда текущего аудио-чанка TTS
  setAmplitude(a) { this.ampTarget = Math.min(1, a * 1.4); }

  // 8 частотных полос голоса (эквалайзер) от PcmPlayer
  setBands(bands) {
    for (let i = 0; i < 8; i++) this.bandTargets[i] = Math.min(1, bands[i]);
  }

  setState(state) {
    this.activity = { idle: 0.1, listening: 0.35, thinking: 0.7, speaking: 0.5 }[state] ?? 0.15;
  }

  _loop() {
    requestAnimationFrame(() => this._loop());
    const dt = this.clock.getDelta();

    // быстрая атака, плавный спад — волны «дышат» вместе с речью
    const k = this.ampTarget > this.amp ? 0.5 : 0.05;
    this.amp += (this.ampTarget - this.amp) * k;
    this.ampTarget *= 0.92;

    // полосы эквалайзера: атака быстрая, спад плавный, затем затухание
    for (let i = 0; i < 8; i++) {
      const kb = this.bandTargets[i] > this.bands[i] ? 0.45 : 0.07;
      this.bands[i] += (this.bandTargets[i] - this.bands[i]) * kb;
      this.bandTargets[i] *= 0.90;
    }

    this.uniforms.uTime.value += dt * (0.8 + this.activity * 0.6 + this.amp * 0.8);
    this.uniforms.uAmp.value = this.amp;
    this.uniforms.uActivity.value += (this.activity - this.uniforms.uActivity.value) * 0.04;

    this.renderer.render(this.scene, this.camera);
  }
}
