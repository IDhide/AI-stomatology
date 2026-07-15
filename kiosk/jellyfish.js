// Процедурная сцена «медузы» для режима ожидания — чистый JavaScript/canvas,
// видеофайл не нужен. Тёмный звёздный фон, полупрозрачные светящиеся медузы
// с пульсирующим куполом и волнистыми щупальцами, медленно плывут вверх.

const PALETTES = [
  { bell: [140, 190, 255], glow: [90, 150, 255] },   // голубая
  { bell: [120, 235, 255], glow: [60, 190, 230] },   // бирюзовая
  { bell: [255, 170, 120], glow: [255, 120, 70] },   // янтарная
  { bell: [200, 140, 255], glow: [150, 80, 255] },   // фиолетовая
  { bell: [255, 150, 200], glow: [255, 90, 160] },   // розовая
];

function rnd(a, b) { return a + Math.random() * (b - a); }

class Jelly {
  constructor(w, h, fromBottom = false) { this.reset(w, h, fromBottom); }

  reset(w, h, fromBottom) {
    this.x = rnd(0.05, 0.95) * w;
    this.y = fromBottom ? h + rnd(60, 300) : rnd(0, h);
    this.size = rnd(28, 86);                    // радиус купола
    this.speed = rnd(8, 22) / this.size * 14;   // маленькие — шустрее
    this.phase = rnd(0, Math.PI * 2);
    this.pulseFreq = rnd(0.6, 1.1);
    this.swayAmp = rnd(10, 34);
    this.swayFreq = rnd(0.08, 0.2);
    this.palette = PALETTES[(Math.random() * PALETTES.length) | 0];
    this.tentacles = 5 + ((Math.random() * 3) | 0);
    this.alpha = rnd(0.55, 0.9);
  }

  update(dt, w, h) {
    this.phase += dt * this.pulseFreq;
    this.y -= this.speed * dt * 10 * (1 + 0.5 * Math.max(0, Math.sin(this.phase)));
    this.x += Math.sin(this.phase * this.swayFreq * 8) * this.swayAmp * dt;
    if (this.y < -this.size * 4) this.reset(w, h, true);
  }

  draw(ctx) {
    const { x, y, size } = this;
    const pulse = 1 + 0.09 * Math.sin(this.phase);        // купол «дышит»
    const squash = 1 - 0.12 * Math.sin(this.phase);
    const [br, bg, bb] = this.palette.bell;
    const [gr, gg, gb] = this.palette.glow;

    ctx.save();
    ctx.translate(x, y);
    ctx.globalCompositeOperation = "lighter";

    // ── щупальца ────────────────────────────────────────────────
    ctx.lineWidth = Math.max(1, size * 0.035);
    for (let i = 0; i < this.tentacles; i++) {
      const t = (i / (this.tentacles - 1) - 0.5) * 2;      // -1..1
      const baseX = t * size * 0.7;
      const len = size * rnd(2.2, 2.4) * (1 - Math.abs(t) * 0.25);
      const sway = Math.sin(this.phase * 1.4 + i) * size * 0.35;
      const grad = ctx.createLinearGradient(0, 0, 0, len);
      grad.addColorStop(0, `rgba(${br},${bg},${bb},${0.5 * this.alpha})`);
      grad.addColorStop(1, `rgba(${gr},${gg},${gb},0)`);
      ctx.strokeStyle = grad;
      ctx.beginPath();
      ctx.moveTo(baseX, size * 0.25);
      ctx.bezierCurveTo(
        baseX + sway * 0.4, len * 0.4,
        baseX - sway, len * 0.75,
        baseX + sway * 0.6, len,
      );
      ctx.stroke();
    }

    // ── свечение вокруг купола ──────────────────────────────────
    const halo = ctx.createRadialGradient(0, 0, size * 0.2, 0, 0, size * 2.4);
    halo.addColorStop(0, `rgba(${gr},${gg},${gb},${0.28 * this.alpha})`);
    halo.addColorStop(1, `rgba(${gr},${gg},${gb},0)`);
    ctx.fillStyle = halo;
    ctx.beginPath();
    ctx.arc(0, 0, size * 2.4, 0, Math.PI * 2);
    ctx.fill();

    // ── купол ───────────────────────────────────────────────────
    ctx.scale(pulse, squash);
    const bell = ctx.createRadialGradient(0, -size * 0.35, size * 0.1, 0, 0, size);
    bell.addColorStop(0, `rgba(255,255,255,${0.85 * this.alpha})`);
    bell.addColorStop(0.35, `rgba(${br},${bg},${bb},${0.55 * this.alpha})`);
    bell.addColorStop(1, `rgba(${gr},${gg},${gb},0.05)`);
    ctx.fillStyle = bell;
    ctx.beginPath();
    ctx.arc(0, 0, size, Math.PI, 0);                       // верхняя половина
    ctx.bezierCurveTo(size * 0.9, size * 0.45, size * 0.4, size * 0.55, 0, size * 0.5);
    ctx.bezierCurveTo(-size * 0.4, size * 0.55, -size * 0.9, size * 0.45, -size, 0);
    ctx.fill();

    ctx.restore();
  }
}

export class JellyfishScene {
  constructor(canvas, count = 8) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.count = count;
    this.running = false;
    this.jellies = [];
    this.stars = [];
    this._last = 0;
    this._resize();
    addEventListener("resize", () => this._resize());
  }

  _resize() {
    this.canvas.width = innerWidth;
    this.canvas.height = innerHeight;
    this.stars = Array.from({ length: 140 }, () => ({
      x: Math.random() * this.canvas.width,
      y: Math.random() * this.canvas.height,
      r: rnd(0.4, 1.6),
      tw: rnd(0.5, 2.5),
      ph: rnd(0, Math.PI * 2),
    }));
  }

  start() {
    if (this.running) return;
    this.running = true;
    const { width: w, height: h } = this.canvas;
    if (!this.jellies.length)
      this.jellies = Array.from({ length: this.count }, () => new Jelly(w, h));
    this._last = performance.now();
    requestAnimationFrame((t) => this._loop(t));
  }

  stop() { this.running = false; }

  _loop(now) {
    if (!this.running) return;
    const dt = Math.min(0.05, (now - this._last) / 1000);
    this._last = now;
    const { ctx, canvas } = this;
    const { width: w, height: h } = canvas;

    // фон: глубина океана/космоса
    const bg = ctx.createLinearGradient(0, 0, 0, h);
    bg.addColorStop(0, "#050312");
    bg.addColorStop(1, "#0a0620");
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    // звёзды/планктон с мерцанием
    ctx.globalCompositeOperation = "lighter";
    const t = now / 1000;
    for (const s of this.stars) {
      const a = 0.25 + 0.55 * (0.5 + 0.5 * Math.sin(t * s.tw + s.ph));
      ctx.fillStyle = `rgba(190,200,255,${a})`;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    }

    for (const j of this.jellies) { j.update(dt, w, h); j.draw(ctx); }

    requestAnimationFrame((tt) => this._loop(tt));
  }
}
