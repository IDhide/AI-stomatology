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
    float wob = (fbm(dir*1.5 + vec2(3.0, t*0.08)) - 0.5) * 0.10
              + (fbm(dir*3.1 + vec2(9.0, t*0.05)) - 0.5) * 0.05;
    float r0 = 0.28 + wob + uAmp*0.02;    // радиус светящегося кольца

    float d = r - r0;

    // ── профиль света: тёмное ядро, компактное кольцо, ореол ──────
    float ring  = exp(-d*d / 0.008);
    float halo  = exp(-max(d, 0.0) * 3.8) * 0.50;
    float core  = smoothstep(0.0, r0*0.92, r);          // затемнение ядра
    float inner = exp(-max(-d, 0.0) * 7.0) * 0.40;      // свет у кромки ядра

    // ── ТОНКИЕ частые волны; речь явно их раскачивает ─────────────
    float speed = 1.4 + uAmp*5.0;                       // говорит → волны бегут
    float wPhase = r*170.0 - t*speed*1.8
                 + fbm(dir*2.0 + vec2(0.0, t*0.10))*5.0;
    float waves  = pow(0.5 + 0.5*sin(wPhase), 3.0);     // тонкие гребни
    float wAmp = 0.06 + uActivity*0.04 + uAmp*0.60;     // тихо — почти гладко
    float lit = (ring*0.9 + halo + inner) * mix(1.0 - wAmp, 1.0, waves);
    lit *= mix(0.08, 1.0, core);                        // ядро остаётся тёмным

    // ── 3D-объём: свет сверху-слева, низ кольца в тени ────────────
    float lightSide = dot(dir, normalize(vec2(-0.35, 0.80)));
    lit *= 0.72 + 0.38*lightSide;

    // ── цвет: ФИОЛЕТОВАЯ гамма (бренд), розовые акценты ───────────
    float hueA = fbm(dir*1.2 + vec2(17.0, t*0.06));
    float hueB = fbm(dir*0.9 + vec2(-7.0, t*0.04));
    vec3 deepViolet = vec3(0.16, 0.06, 0.45);
    vec3 violet     = vec3(0.46, 0.20, 0.96);   // #7b3ff2 — бренд
    vec3 magenta    = vec3(0.72, 0.28, 0.95);
    vec3 pink       = vec3(0.95, 0.55, 0.95);
    vec3 blueAccent = vec3(0.28, 0.28, 0.95);

    vec3 col = mix(deepViolet, violet, smoothstep(0.15, 0.60, hueA));
    col = mix(col, magenta, smoothstep(0.55, 0.85, hueB) * 0.8);
    col = mix(col, pink,   smoothstep(0.80, 0.97, hueA) * 0.6);
    col = mix(col, blueAccent, smoothstep(0.20, 0.0, hueA) * 0.25);

    // ── фон: глубокий тёмно-фиолетовый с 3D-градиентом ядра ───────
    vec3 bg = mix(vec3(0.050, 0.022, 0.120), vec3(0.014, 0.007, 0.040),
                  smoothstep(0.0, 1.15, r));
    // ядро не плоское: мягкий объёмный градиент, светлее к верху
    bg += vec3(0.10, 0.05, 0.24) * exp(-r*3.0)
        * (0.35 + 0.30*dot(dir, vec2(0.0, 1.0))) * (1.0 - core);

    vec3 final = bg + col * lit * (0.55 + uAmp*0.55);

    // виньетирование — компактная «сфера света» в тёмном поле
    final *= 1.0 - 0.42*smoothstep(0.55, 1.25, r);

    // ── объёмный 3D-шар в центре (как на референсе) ───────────────
    float sr = 0.185 + uAmp*0.012 + uActivity*0.004;    // дышит с голосом
    float sd = r - sr;
    float sphereMask = smoothstep(0.008, -0.008, sd);

    if (sphereMask > 0.0) {
      // нормаль точки сферы — честное 3D
      float nz = sqrt(max(1.0 - (r*r)/(sr*sr), 0.0));
      vec3 N = vec3(uv/sr, nz);
      // лёгкая органическая рябь поверхности при речи
      float bump = (fbm(uv*7.0 + vec2(t*0.25, -t*0.18)) - 0.5) * (0.15 + uAmp*0.6);
      N = normalize(N + vec3(bump*0.25));

      vec3 L = normalize(vec3(-0.38, 0.70, 0.55));      // свет сверху-слева
      float lam = clamp(dot(N, L), 0.0, 1.0);

      vec3 sBase = vec3(0.16, 0.06, 0.42);              // тень
      vec3 sMid  = vec3(0.44, 0.20, 0.94);              // бренд-фиолет
      vec3 sHi   = vec3(0.80, 0.64, 1.00);              // блик-лаванда

      vec3 sc = mix(sBase, sMid, smoothstep(0.0, 0.85, lam));
      sc = mix(sc, sHi, pow(lam, 4.0) * 0.85);          // мягкий верхний блик
      float rimS = pow(1.0 - nz, 2.6);                  // светящаяся кромка
      sc += vec3(0.52, 0.32, 1.00) * rimS * 0.55;
      sc *= 1.0 + uAmp*0.45;                            // голос подсвечивает
      sc *= 0.97 + 0.06*fbm(uv*5.0 + t*0.1);            // живая поверхность

      final = mix(final, sc, sphereMask);
    }
    // свечение сразу за кромкой шара — связывает его с туманностью
    final += violet * exp(-max(sd, 0.0) * 26.0) * (0.20 + uAmp*0.25)
           * (1.0 - sphereMask);

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
