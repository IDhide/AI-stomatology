// Процедурная сцена «медузы» для режима ожидания — реалистичный стиль.
// Полупрозрачные лунные медузы: светящийся край купола, четыре гонады
// внутри (как у настоящей Aurelia aurita), десятки тонких щупалец и
// волнистые ротовые лопасти. Глубина: дальние — мельче, тусклее, размытее.

function rnd(a, b) { return a + Math.random() * (b - a); }

class Jelly {
  constructor(w, h, fromBottom = false) { this.reset(w, h, fromBottom); }

  reset(w, h, fromBottom) {
    this.depth = Math.random();                    // 0 — близко, 1 — далеко
    const near = 1 - this.depth;
    this.x = rnd(0.05, 0.95) * w;
    this.y = fromBottom ? h + rnd(100, 500) : rnd(0, h);
    this.size = rnd(60, 110) * (0.35 + near * 0.65);
    this.speed = rnd(5, 9) * (0.5 + near * 0.5);
    this.phase = rnd(0, Math.PI * 2);
    this.pulseFreq = rnd(0.35, 0.6);               // медленное «дыхание»
    this.swayAmp = rnd(6, 18);
    this.tilt = rnd(-0.25, 0.25);
    this.tiltFreq = rnd(0.05, 0.12);
    // фирменная гамма: фиолетово-сиреневые, реже — розово-магентовые
    this.hue = Math.random() < 0.7 ? rnd(255, 285) : rnd(295, 320);
    this.alpha = (0.55 + near * 0.50);
    this.tentacles = 24;
    this.blur = this.depth * 3.5;                  // дальние — мягче
  }

  update(dt, w, h) {
    this.phase += dt * this.pulseFreq * Math.PI * 2;
    const thrust = Math.max(0, Math.sin(this.phase)) ** 2;
    this.y -= this.speed * dt * (6 + thrust * 22);
    this.x += Math.sin(this.phase * 0.23) * this.swayAmp * dt;
    if (this.y < -this.size * 5) this.reset(w, h, true);
  }

  draw(ctx) {
    const { size, hue, alpha } = this;
    const pulse = Math.sin(this.phase);
    const bellW = 1 + 0.06 * pulse;                // купол чуть расширяется…
    const bellH = 1 - 0.10 * pulse;                // …и сплющивается
    const tiltNow = this.tilt * Math.sin(this.phase * this.tiltFreq * 8);

    ctx.save();
    ctx.translate(this.x, this.y);
    ctx.rotate(tiltNow);
    if (this.blur > 0.5) ctx.filter = `blur(${this.blur.toFixed(1)}px)`;
    ctx.globalCompositeOperation = "lighter";

    // ── ротовые лопасти (4 волнистые полупрозрачные ленты) ────────
    for (let i = 0; i < 4; i++) {
      const bx = (i / 3 - 0.5) * size * 0.5;
      const len = size * 1.7;
      const sw = Math.sin(this.phase * 0.9 + i * 1.7) * size * 0.28;
      const grad = ctx.createLinearGradient(0, 0, 0, len);
      grad.addColorStop(0, `hsla(${hue}, 60%, 80%, ${0.20 * alpha})`);
      grad.addColorStop(1, `hsla(${hue}, 70%, 65%, 0)`);
      ctx.strokeStyle = grad;
      ctx.lineWidth = size * 0.10;
      ctx.beginPath();
      ctx.moveTo(bx * 0.5, size * 0.30);
      ctx.bezierCurveTo(bx + sw * 0.5, len * 0.35, bx - sw, len * 0.7, bx + sw, len);
      ctx.stroke();
      // светлый гребень ленты
      ctx.lineWidth = size * 0.03;
      ctx.strokeStyle = `hsla(${hue}, 40%, 92%, ${0.18 * alpha})`;
      ctx.stroke();
    }

    // ── тонкие краевые щупальца: длинные, плавные S-изгибы ────────
    ctx.lineWidth = Math.max(0.5, size * 0.010);
    for (let i = 0; i < this.tentacles; i++) {
      const t = (i / (this.tentacles - 1) - 0.5) * 2;
      const baseX = t * size * 0.92 * bellW;
      const len = size * (2.2 + (i % 5) * 0.18) * (1 - t * t * 0.25);
      const s1 = Math.sin(this.phase * 0.9 + i * 0.8) * size * 0.20 * (1 - Math.abs(t) * 0.3);
      const s2 = Math.sin(this.phase * 0.9 + i * 0.8 + 1.8) * size * 0.26;
      const grad = ctx.createLinearGradient(0, 0, 0, len);
      grad.addColorStop(0, `hsla(${hue}, 45%, 85%, ${0.30 * alpha})`);
      grad.addColorStop(1, `hsla(${hue}, 60%, 70%, 0)`);
      ctx.strokeStyle = grad;
      ctx.beginPath();
      ctx.moveTo(baseX, size * 0.18);
      ctx.bezierCurveTo(baseX + s1, len * 0.35, baseX - s2 * 0.7, len * 0.7, baseX + s2, len);
      ctx.stroke();
    }

    // ── купол ─────────────────────────────────────────────────────
    ctx.save();
    ctx.scale(bellW, bellH);

    // тело купола: почти прозрачное, светлеет к макушке
    const bell = ctx.createRadialGradient(0, -size * 0.25, size * 0.05, 0, 0, size);
    bell.addColorStop(0.0, `hsla(${hue}, 35%, 96%, ${0.42 * alpha})`);
    bell.addColorStop(0.5, `hsla(${hue}, 60%, 82%, ${0.20 * alpha})`);
    bell.addColorStop(0.92, `hsla(${hue}, 70%, 72%, ${0.08 * alpha})`);
    bell.addColorStop(1.0, `hsla(${hue}, 70%, 70%, 0)`);
    ctx.fillStyle = bell;
    ctx.beginPath();
    ctx.arc(0, 0, size, Math.PI, 0);
    ctx.bezierCurveTo(size * 0.95, size * 0.28, size * 0.45, size * 0.4, 0, size * 0.36);
    ctx.bezierCurveTo(-size * 0.45, size * 0.4, -size * 0.95, size * 0.28, -size, 0);
    ctx.fill();

    // мягкое свечение края купола: короткие дуги с круглыми концами,
    // ярче у макушки, растворяются к краям — без «шлема»
    ctx.lineCap = "round";
    const rimSegs = [
      { from: Math.PI * 1.15, to: Math.PI * 1.85, w: 0.030, a: 0.28 },
      { from: Math.PI * 1.30, to: Math.PI * 1.60, w: 0.014, a: 0.50 },
    ];
    for (const s of rimSegs) {
      ctx.lineWidth = size * s.w;
      ctx.strokeStyle = `hsla(${hue}, 40%, 94%, ${s.a * alpha})`;
      ctx.beginPath();
      ctx.arc(0, 0, size * 0.97, s.from, s.to);
      ctx.stroke();
    }

    // четыре гонады-кольца ромбом вокруг центра (как у лунной медузы)
    const gonadPos = [
      [0, -size * 0.34], [size * 0.20, -size * 0.16],
      [0, -size * 0.02], [-size * 0.20, -size * 0.16],
    ];
    for (const [gx, gy] of gonadPos) {
      const g = ctx.createRadialGradient(gx, gy, size * 0.02, gx, gy, size * 0.13);
      g.addColorStop(0, `hsla(${hue}, 35%, 95%, ${0.10 * alpha})`);
      g.addColorStop(0.65, `hsla(${hue}, 45%, 88%, ${0.30 * alpha})`);
      g.addColorStop(1, `hsla(${hue}, 60%, 75%, 0)`);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.ellipse(gx, gy, size * 0.13, size * 0.10, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    ctx.restore();
  }
}

export class JellyfishScene {
  constructor(canvas, count = 7) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.count = count;
    this.running = false;
    this.jellies = [];
    this.motes = [];
    this._last = 0;
    this._resize();
    addEventListener("resize", () => this._resize());
  }

  _resize() {
    this.canvas.width = innerWidth;
    this.canvas.height = innerHeight;
    // «морской снег» — взвесь, а не звёзды
    this.motes = Array.from({ length: 110 }, () => ({
      x: Math.random() * this.canvas.width,
      y: Math.random() * this.canvas.height,
      r: rnd(0.3, 1.3),
      vy: rnd(2, 7),
      a: rnd(0.05, 0.30),
    }));
  }

  start() {
    if (this.running) return;
    this.running = true;
    const { width: w, height: h } = this.canvas;
    if (!this.jellies.length) {
      this.jellies = Array.from({ length: this.count }, () => new Jelly(w, h));
      this.jellies.sort((a, b) => b.depth - a.depth); // дальние рисуем первыми
    }
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

    // глубина: тёмно-фиолетовая толща воды (бренд-гамма)
    const bg = ctx.createLinearGradient(0, 0, 0, h);
    bg.addColorStop(0, "#140a33");
    bg.addColorStop(0.5, "#0b0620");
    bg.addColorStop(1, "#050310");
    ctx.globalCompositeOperation = "source-over";
    ctx.filter = "none";
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    // лучи света сверху
    ctx.globalCompositeOperation = "lighter";
    const t = now / 1000;
    for (let i = 0; i < 3; i++) {
      const lx = w * (0.2 + i * 0.3) + Math.sin(t * 0.05 + i * 2) * w * 0.06;
      const lg = ctx.createLinearGradient(lx, 0, lx + w * 0.06, h * 0.8);
      lg.addColorStop(0, "rgba(140,95,255,0.05)");
      lg.addColorStop(1, "rgba(140,95,255,0)");
      ctx.fillStyle = lg;
      ctx.beginPath();
      ctx.moveTo(lx - w * 0.02, 0);
      ctx.lineTo(lx + w * 0.05, 0);
      ctx.lineTo(lx + w * 0.16, h * 0.85);
      ctx.lineTo(lx - w * 0.10, h * 0.85);
      ctx.fill();
    }

    // морской снег медленно опускается
    for (const m of this.motes) {
      m.y += m.vy * dt * 3;
      if (m.y > h) { m.y = -4; m.x = Math.random() * w; }
      ctx.fillStyle = `rgba(195,175,245,${m.a})`;
      ctx.beginPath();
      ctx.arc(m.x, m.y, m.r, 0, Math.PI * 2);
      ctx.fill();
    }

    for (const j of this.jellies) { j.update(dt, w, h); j.draw(ctx); }
    ctx.filter = "none";

    requestAnimationFrame((tt) => this._loop(tt));
  }
}
