// Визуализатор «плазменная туманность» — точно по референс-видео:
// тёмное ядро, вокруг — мягкое светящееся сине-фиолетовое кольцо с розовыми
// акцентами, всё диффузное, по полю расходятся тонкие концентрические волны.
// Полноэкранный фрагментный шейдер; голос усиливает волны и яркость.
import * as THREE from "three";

const VERT = /* glsl */ `
  void main() { gl_Position = vec4(position, 1.0); }
`;

const FRAG = /* glsl */ `
  precision highp float;
  uniform vec2  uRes;
  uniform float uTime;
  uniform float uAmp;      // 0..1 голос
  uniform float uActivity; // «дыхание» состояния

  // ── value noise + fbm ──────────────────────────────────────────
  float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453123); }
  float noise(vec2 p){
    vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
    return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),
               mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);
  }
  float fbm(vec2 p){
    float v=0.0, a=0.5;
    for(int i=0;i<4;i++){ v+=a*noise(p); p*=2.03; a*=0.5; }
    return v;
  }

  void main(){
    vec2 uv = (gl_FragCoord.xy - 0.5*uRes) / min(uRes.x, uRes.y);
    float r = length(uv);
    // направление вместо угла — нет шва на границе atan
    vec2 dir = uv / max(r, 1e-4);
    float t = uTime;

    // ── органическая (не круглая) форма кольца ────────────────────
    float wob = (fbm(dir*1.4 + vec2(7.0, t*0.10)) - 0.5) * 0.14
              + (fbm(dir*2.9 + vec2(-3.0, t*0.06)) - 0.5) * 0.07;
    float r0 = 0.31 + wob + uAmp*0.02;    // радиус светящегося кольца

    float d = r - r0;

    // ── профиль света: тёмное ядро, мягкое кольцо, широкий ореол ──
    float ring  = exp(-d*d / 0.010);
    float halo  = exp(-max(d, 0.0) * 3.2) * 0.55;
    float core  = smoothstep(0.0, r0*0.95, r);          // затемнение ядра
    float inner = exp(-max(-d, 0.0) * 6.0) * 0.45;      // свет у кромки ядра

    // ── тонкие концентрические волны (главная фишка референса) ───
    float wPhase = r*120.0 - t*2.2 + fbm(dir*2.2 + vec2(0.0, t*0.15))*6.0;
    float waves  = 0.5 + 0.5*sin(wPhase);
    waves = pow(waves, 2.0);                            // тонкие гребни
    float wAmp = 0.10 + uActivity*0.06 + uAmp*0.38;     // голос раскачивает волны
    float lit = (ring*0.85 + halo + inner) * mix(1.0 - wAmp, 1.0, waves);
    lit *= mix(0.10, 1.0, core);                        // ядро остаётся тёмным

    // ── цвет: глубокая синева, фиолет и розовые акценты ───────────
    float hueA = fbm(dir*1.1 + vec2(21.0, t*0.08));
    float hueB = fbm(dir*0.8 + vec2(-11.0, t*0.05));
    vec3 deepBlue = vec3(0.06, 0.10, 0.65);
    vec3 blue     = vec3(0.12, 0.25, 0.95);
    vec3 violet   = vec3(0.38, 0.18, 0.95);
    vec3 pink     = vec3(0.85, 0.38, 0.90);
    vec3 cyan     = vec3(0.25, 0.55, 1.00);

    vec3 col = mix(deepBlue, blue, smoothstep(0.2, 0.65, hueA));
    col = mix(col, violet, smoothstep(0.5, 0.85, hueB));
    col = mix(col, pink,   smoothstep(0.78, 0.97, hueA) * 0.7);
    col = mix(col, cyan,   smoothstep(0.25, 0.0, hueB) * 0.3);

    // ── фон: глубокая тёмная синева, как на видео ─────────────────
    vec3 bg = mix(vec3(0.025, 0.03, 0.14), vec3(0.008, 0.010, 0.05),
                  smoothstep(0.0, 1.2, r));

    vec3 final = bg + col * lit * (0.50 + uAmp*0.45);

    // виньетирование
    final *= 1.0 - 0.35*smoothstep(0.6, 1.35, r);

    gl_FragColor = vec4(final, 1.0);
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

    this.uniforms = {
      uRes: { value: new THREE.Vector2(1, 1) },
      uTime: { value: 0 },
      uAmp: { value: 0 },
      uActivity: { value: 0.15 },
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

    this.uniforms.uTime.value += dt * (0.8 + this.activity * 0.6 + this.amp * 0.8);
    this.uniforms.uAmp.value = this.amp;
    this.uniforms.uActivity.value += (this.activity - this.uniforms.uActivity.value) * 0.04;

    this.renderer.render(this.scene, this.camera);
  }
}
