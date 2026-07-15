// Фиолетовая сфера в стиле референса «OLIVIA AI»: гладкий шар с мягким
// градиентом и большим ореолом-свечением. Реакция на голос — плавная
// пульсация масштаба и яркости + едва заметная органическая рябь,
// а не «шипы» из шума.
import * as THREE from "three";

const VERT = /* glsl */ `
  uniform float uTime;
  uniform float uAmp;      // 0..1 амплитуда голоса
  uniform float uActivity; // базовое «дыхание» по состоянию
  varying vec3 vNormal;
  varying vec3 vView;

  // компактный 3D-шум (достаточно для мягкой ряби)
  float hash(vec3 p){ return fract(sin(dot(p, vec3(127.1,311.7,74.7)))*43758.5453); }
  float noise(vec3 p){
    vec3 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
    return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),
                   mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),
               mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),
                   mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);
  }

  void main(){
    vNormal = normalize(normalMatrix * normal);
    // общий пульс: дыхание + голос
    float scale = 1.0 + uActivity*0.02 + uAmp*0.06;
    // мягкая органическая рябь, заметная только при речи
    float ripple = (noise(normal*3.0 + uTime*0.6) - 0.5) * (0.006 + uAmp*0.05);
    vec3 pos = position * scale + normal * ripple;
    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    vView = -mv.xyz;
    gl_Position = projectionMatrix * mv;
  }
`;

const FRAG = /* glsl */ `
  uniform float uAmp;
  varying vec3 vNormal;
  varying vec3 vView;

  void main(){
    vec3 N = normalize(vNormal);
    vec3 V = normalize(vView);

    // палитра как на референсе: глубокий фиолет → светлая сердцевина
    vec3 deep  = vec3(0.26, 0.10, 0.62);
    vec3 mid   = vec3(0.48, 0.24, 0.96);
    vec3 light = vec3(0.76, 0.58, 1.00);

    // свет сверху-спереди — даёт мягкий объём, как у матового шара
    vec3 L = normalize(vec3(0.25, 0.55, 1.0));
    float lambert = clamp(dot(N, L), 0.0, 1.0);

    vec3 col = mix(deep, mid, smoothstep(0.0, 0.75, lambert));
    col = mix(col, light, pow(lambert, 3.0) * 0.85);

    // мягкий светящийся край (subsurface-эффект)
    float rim = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 2.2);
    col += vec3(0.45, 0.28, 0.95) * rim * 0.55;

    // голос делает шар ярче
    col *= 1.0 + uAmp * 0.55;

    gl_FragColor = vec4(col, 1.0);
  }
`;

// Текстура ореола: мягкий радиальный градиент
function makeHaloTexture() {
  const c = document.createElement("canvas");
  c.width = c.height = 512;
  const ctx = c.getContext("2d");
  const g = ctx.createRadialGradient(256, 256, 60, 256, 256, 256);
  g.addColorStop(0, "rgba(123,63,242,0.55)");
  g.addColorStop(0.4, "rgba(110,50,230,0.22)");
  g.addColorStop(1, "rgba(90,40,200,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 512, 512);
  return new THREE.CanvasTexture(c);
}

export class Visualizer {
  constructor(canvas) {
    this.canvas = canvas;
    this.amp = 0;
    this.ampTarget = 0;
    this.activity = 0.15;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
    this.camera.position.z = 4.2;

    this.uniforms = {
      uTime: { value: 0 },
      uAmp: { value: 0 },
      uActivity: { value: 0.15 },
    };

    // ореол позади шара
    this.halo = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: makeHaloTexture(),
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    this.halo.scale.set(5.2, 5.2, 1);
    this.scene.add(this.halo);

    const geo = new THREE.SphereGeometry(1.15, 128, 128);
    const mat = new THREE.ShaderMaterial({
      uniforms: this.uniforms, vertexShader: VERT, fragmentShader: FRAG,
    });
    this.mesh = new THREE.Mesh(geo, mat);
    this.scene.add(this.mesh);

    this.resize();
    addEventListener("resize", () => this.resize());
    this.clock = new THREE.Clock();
    this._loop();
  }

  resize() {
    const w = innerWidth, h = innerHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  // 0..1 — амплитуда текущего аудио-чанка TTS
  setAmplitude(a) { this.ampTarget = Math.min(1, a); }

  setState(state) {
    this.activity = { idle: 0.05, listening: 0.3, thinking: 0.6, speaking: 0.4 }[state] ?? 0.15;
  }

  _loop() {
    requestAnimationFrame(() => this._loop());
    const dt = this.clock.getDelta();
    const t = this.uniforms.uTime.value += dt;

    // сглаживание: быстрая атака, плавный спад
    const k = this.ampTarget > this.amp ? 0.45 : 0.06;
    this.amp += (this.ampTarget - this.amp) * k;
    this.ampTarget *= 0.9;

    this.uniforms.uAmp.value = this.amp;
    this.uniforms.uActivity.value += (this.activity - this.uniforms.uActivity.value) * 0.04;

    // лёгкое «дыхание» в покое + отклик ореола на голос
    const breathe = 1 + Math.sin(t * 1.4) * 0.012 * (1 + this.activity);
    this.mesh.scale.setScalar(breathe);
    const haloScale = 5.2 * (1 + this.amp * 0.25 + Math.sin(t * 1.4) * 0.02);
    this.halo.scale.set(haloScale, haloScale, 1);
    this.halo.material.opacity = 0.75 + this.amp * 0.25;

    this.mesh.rotation.y += dt * 0.05;
    this.renderer.render(this.scene, this.camera);
  }
}
