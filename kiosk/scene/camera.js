// Движение виртуальной камеры (ТЗ §9): медленный noise-дрейф, малая амплитуда,
// без резких вращений и головокружения. Камера всегда смотрит около центра.
import * as THREE from "three";

// дешёвый детерминированный шум (value noise) на CPU
function vnoise(x) {
  const i = Math.floor(x), f = x - i;
  const a = Math.sin(i * 127.1) * 43758.5453 % 1;
  const b = Math.sin((i + 1) * 127.1) * 43758.5453 % 1;
  const u = f * f * (3 - 2 * f);
  return (a + (b - a) * u);
}

export class CameraRig {
  constructor(camera, cfg) {
    this.camera = camera;
    this.drift = cfg.camera.driftIntensity;
    this.zoom = cfg.camera.zoomIntensity;
    this.t = Math.random() * 100;
    this.baseZ = 6.2;
    this.look = new THREE.Vector3(0, -0.3, 0);
  }

  update(dt) {
    this.t += dt;
    const t = this.t;
    // независимые медленные оси
    const x = (vnoise(t * 0.05) - 0.5) * 2 * this.drift * 6;
    const y = (vnoise(t * 0.037 + 10) - 0.5) * 2 * this.drift * 3;
    const z = this.baseZ + (vnoise(t * 0.028 + 20) - 0.5) * 2 * this.zoom * 10;

    this.camera.position.x += (x - this.camera.position.x) * Math.min(1, dt * 0.8);
    this.camera.position.y += (y - this.camera.position.y) * Math.min(1, dt * 0.8);
    this.camera.position.z += (z - this.camera.position.z) * Math.min(1, dt * 0.8);

    // очень мягкое изменение направления взгляда
    this.look.x += ((vnoise(t * 0.03 + 5) - 0.5) * 0.6 - this.look.x) * Math.min(1, dt * 0.5);
    this.camera.lookAt(this.look);
  }
}
