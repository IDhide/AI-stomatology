// Фоновый слой (ТЗ §6.1): глубокий анимированный градиент + procedural noise,
// медленно плывущие цветовые облака, эффект глубины и лёгкий световой туман.
// Реализован как плоскость-ребёнок камеры — всегда заполняет кадр.
import * as THREE from "three";
import { SNOISE } from "./glsl.js";
import { PALETTE } from "./config.js";

const c = (hex) => new THREE.Color(hex);

const VERT = /* glsl */ `
  varying vec2 vUv;
  void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
`;

const FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform float uTime;
  uniform float uAspect;
  uniform vec3  uC0; // почти чёрный
  uniform vec3  uC1; // тёмно-синий
  uniform vec3  uC2; // глубокий фиолет
  uniform vec3  uC3; // холодный бирюзовый акцент
  uniform vec3  uTint;      // цветовой сдвиг (кинематографические события)
  uniform float uTintAmt;
  uniform float uCorePulse; // 0..1 подсветка из-под ядра
  ${SNOISE}

  float fbmScale(vec2 p, float t){
    float a = 0.5, s = 0.0;
    vec3 q = vec3(p * 1.1 + vec2(t, t*0.4), t*0.8);
    for(int i=0;i<4;i++){ s += a*snoise(q); q*=2.03; a*=0.5; }
    return s*0.5 + 0.5;
  }

  void main(){
    vec2 uv = vUv;
    vec2 p = (uv - 0.5) * vec2(uAspect, 1.0);

    // вертикальный градиент глубины: сверху темнее, снизу — тёплый фиолет
    vec3 col = mix(uC1, uC0, pow(1.0 - uv.y, 1.3));

    // очень медленно плывущие цветовые облака
    float t = uTime * 0.02;
    float cloud  = fbmScale(p, t);
    float cloud2 = snoise(vec3(p * 0.8 - vec2(t*0.6, t*0.3), t*0.5 + 4.0));

    col = mix(col, uC2, smoothstep(0.15, 0.9, cloud) * 0.55);
    col = mix(col, uC1, smoothstep(0.20, 0.95, cloud2) * 0.35);

    // редкие бирюзовые «просветы» в верхней части
    float teal = smoothstep(0.55, 1.0, snoise(vec3(p*1.4 + vec2(t*0.4, -t), t*0.7)));
    col += uC3 * teal * 0.10 * smoothstep(0.2, 1.0, uv.y);

    // подсветка из-под центрального ядра
    float d = length(p - vec2(0.0, -0.06));
    col += uC2 * uCorePulse * 0.35 * exp(-d*d*3.0);

    // цветовой сдвиг события
    col = mix(col, col + uTint, uTintAmt);

    // виньетка + мягкий туман по краям — усиливает глубину
    float vig = smoothstep(1.25, 0.2, length(p));
    col *= mix(0.55, 1.0, vig);

    // лёгкое зерно против бандинга градиента
    col += snoise(vec3(uv*900.0, uTime)) * 0.008;

    gl_FragColor = vec4(col, 1.0);
  }
`;

export class Background {
  constructor(camera) {
    this.uniforms = {
      uTime: { value: 0 },
      uAspect: { value: innerWidth / innerHeight },
      uC0: { value: c(PALETTE.bg[0]) },
      uC1: { value: c(PALETTE.bg[2]) },
      uC2: { value: c(PALETTE.bg[4]) },
      uC3: { value: c(PALETTE.bg[6]) },
      uTint: { value: new THREE.Color(0, 0, 0) },
      uTintAmt: { value: 0 },
      uCorePulse: { value: 0 },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      vertexShader: VERT,
      fragmentShader: FRAG,
      depthWrite: false,
      depthTest: false,
      fog: false,
    });
    const geo = new THREE.PlaneGeometry(2, 2);
    this.mesh = new THREE.Mesh(geo, mat);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = -1000;
    this.mesh.position.z = -10;
    this._fit(camera);
    camera.add(this.mesh);
  }

  _fit(camera) {
    const dist = 10;
    const h = 2 * Math.tan((camera.fov * Math.PI) / 360) * dist * 1.2;
    const w = h * camera.aspect * 1.2;
    this.mesh.scale.set(w, h, 1);
  }

  resize(camera) {
    this.uniforms.uAspect.value = camera.aspect;
    this._fit(camera);
  }

  setTint(color, amount) {
    if (color) this.uniforms.uTint.value.copy(color);
    this.uniforms.uTintAmt.value = amount;
  }

  setCorePulse(v) { this.uniforms.uCorePulse.value = v; }

  update(dt) { this.uniforms.uTime.value += dt; }
}
