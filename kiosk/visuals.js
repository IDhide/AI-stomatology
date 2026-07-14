// Реактивный фиолетовый шар на Three.js.
// Вершины икосаэдра смещаются 3D-шумом; сила смещения = амплитуда речи ИИ.
// Состояния: listening (спокойный пульс) · thinking (медленный вихрь) ·
// speaking (реакция на амплитуду).
import * as THREE from "three";

const VERT = /* glsl */ `
  uniform float uTime;
  uniform float uAmp;      // 0..1 амплитуда голоса
  uniform float uActivity; // базовое «дыхание» по состоянию
  varying float vDisp;
  varying vec3 vNormal;

  // --- simplex noise (Ashima) ---
  vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
  vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
  vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
  vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
  float snoise(vec3 v){
    const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
    vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
    vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
    vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
    i=mod289(i);
    vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
    float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
    vec4 j=p-49.0*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
    vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
    vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
    vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
    vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
    vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
    vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
    p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
    vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
    return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
  }

  void main(){
    vNormal = normal;
    float t = uTime * 0.35;
    float n = snoise(normal * 1.8 + t);
    float amp = 0.10 + uActivity * 0.10 + uAmp * 0.55;
    float disp = n * amp;
    vDisp = disp;
    vec3 pos = position + normal * disp;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

const FRAG = /* glsl */ `
  uniform float uAmp;
  varying float vDisp;
  varying vec3 vNormal;
  void main(){
    vec3 core = vec3(0.36, 0.14, 0.85);   // глубокий фиолет
    vec3 glow = vec3(0.65, 0.42, 1.0);    // светлый край
    float f = smoothstep(-0.15, 0.35, vDisp);
    vec3 col = mix(core, glow, f + uAmp * 0.4);
    float rim = pow(1.0 - abs(vNormal.z), 2.0);
    col += glow * rim * 0.6;
    gl_FragColor = vec4(col, 1.0);
  }
`;

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
    const geo = new THREE.IcosahedronGeometry(1.25, 64);
    const mat = new THREE.ShaderMaterial({
      uniforms: this.uniforms, vertexShader: VERT, fragmentShader: FRAG,
    });
    this.mesh = new THREE.Mesh(geo, mat);
    this.scene.add(this.mesh);

    // мягкое свечение вокруг
    const halo = new THREE.PointLight(0x7b3ff2, 2, 10);
    halo.position.set(0, 0, 3);
    this.scene.add(halo);

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

  // 0..1 — амплитуда текущего аудио-чанка от TTS
  setAmplitude(a) { this.ampTarget = Math.min(1, a); }

  setState(state) {
    // базовое «дыхание» и скорость вращения зависят от состояния
    this.activity = { idle: 0.05, listening: 0.25, thinking: 0.5, speaking: 0.35 }[state] ?? 0.15;
  }

  _loop() {
    requestAnimationFrame(() => this._loop());
    const dt = this.clock.getDelta();
    // сглаживаем амплитуду (атака быстрая, спад плавный)
    const k = this.ampTarget > this.amp ? 0.5 : 0.08;
    this.amp += (this.ampTarget - this.amp) * k;
    this.ampTarget *= 0.9;

    this.uniforms.uTime.value += dt * (1 + this.activity);
    this.uniforms.uAmp.value = this.amp;
    this.uniforms.uActivity.value += (this.activity - this.uniforms.uActivity.value) * 0.05;

    this.mesh.rotation.y += dt * (0.15 + this.activity * 0.4);
    this.mesh.rotation.x += dt * 0.05;
    this.renderer.render(this.scene, this.camera);
  }
}
