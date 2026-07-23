// Световые лучи (ТЗ §6.3): мягкие, размытые, без явного источника, медленно
// плывут сверху. Аддитивная плоскость-ребёнок камеры, поверх фона.
import * as THREE from "three";
import { SNOISE } from "./glsl.js";

const VERT = /* glsl */ `
  varying vec2 vUv;
  void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
`;

const FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform float uTime;
  uniform float uAspect;
  uniform float uBoost;   // временное усиление (событие §19)
  ${SNOISE}

  void main(){
    vec2 uv = vUv;
    // наклонённая координата — лучи идут сверху под небольшим углом
    float x = uv.x + (1.0 - uv.y) * 0.18;
    float t = uTime * 0.03;

    // несколько мягких вертикальных полос, промодулированных шумом
    float beams = 0.0;
    beams += smoothstep(0.35, 1.0, 0.5 + 0.5*sin((x*6.0)  + snoise(vec3(x*2.0, t, 0.0))*1.5));
    beams += smoothstep(0.55, 1.0, 0.5 + 0.5*sin((x*3.3) - 1.7 + snoise(vec3(x*1.3, t*0.7, 2.0))*1.2));
    beams *= 0.5;

    // затухание сверху вниз + мягкие края
    float fade = smoothstep(0.0, 0.55, uv.y);            // ярче сверху
    float edges = smoothstep(0.0, 0.2, uv.x) * smoothstep(1.0, 0.8, uv.x);
    float intensity = beams * fade * edges;

    // редкие плавные изменения общей интенсивности
    intensity *= 0.55 + 0.45 * (0.5 + 0.5*sin(uTime*0.11));
    intensity *= (0.10 + uBoost);   // базово очень тускло

    vec3 col = mix(vec3(0.30,0.55,0.85), vec3(0.55,0.45,0.9), uv.y);
    gl_FragColor = vec4(col * intensity, intensity);
  }
`;

export class LightRays {
  constructor(camera) {
    this.uniforms = {
      uTime: { value: 0 },
      uAspect: { value: camera.aspect },
      uBoost: { value: 0 },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms: this.uniforms,
      vertexShader: VERT,
      fragmentShader: FRAG,
      transparent: true,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
      fog: false,
    });
    const geo = new THREE.PlaneGeometry(2, 2);
    this.mesh = new THREE.Mesh(geo, mat);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = -900;
    this.mesh.position.z = -9;
    this._fit(camera);
    camera.add(this.mesh);
    this._boostTarget = 0;
  }

  _fit(camera) {
    const dist = 9;
    const h = 2 * Math.tan((camera.fov * Math.PI) / 360) * dist * 1.2;
    const w = h * camera.aspect * 1.2;
    this.mesh.scale.set(w, h, 1);
  }

  resize(camera) {
    this.uniforms.uAspect.value = camera.aspect;
    this._fit(camera);
  }

  boost(v) { this._boostTarget = v; }

  update(dt) {
    this.uniforms.uTime.value += dt;
    const u = this.uniforms.uBoost;
    u.value += (this._boostTarget - u.value) * Math.min(1, dt * 1.5);
    this._boostTarget *= 0.995;
  }
}
