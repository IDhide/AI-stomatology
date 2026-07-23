// Аудио-слой киоска: захват микрофона (с AEC) + потоковый плеер PCM16.

const TARGET_SR = 16000;

// ── Понижающая передискретизация Float32 → 16 kHz ────────────────────
function downsample(input, inRate, outRate = TARGET_SR) {
  if (inRate === outRate) return input;
  const ratio = inRate / outRate;
  const outLen = Math.round(input.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) out[i] = input[Math.floor(i * ratio)];
  return out;
}

function floatToPcm16(f32) {
  const pcm = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm;
}

// ── Захват микрофона с автоматической детекцией реплики (VAD) ────────
export class MicCapture {
  constructor({ onUtteranceStart, onChunk, onUtteranceEnd }) {
    this.onUtteranceStart = onUtteranceStart;
    this.onChunk = onChunk;          // (Int16Array) во время речи
    this.onUtteranceEnd = onUtteranceEnd;
    this.speaking = false;
    this.silenceMs = 0;
    this.enabled = false;            // «слушаем ли сейчас пациента»
    this.SILENCE_LIMIT = 800;        // мс тишины = конец фразы
    this.THRESH = 0.012;             // порог энергии (RMS)
  }

  async init() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,   // ← ИИ не слышит сам себя (из ТЗ)
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    this.ctx = new AudioContext();
    const src = this.ctx.createMediaStreamSource(stream);
    const proc = this.ctx.createScriptProcessor(2048, 1, 1);
    src.connect(proc);
    proc.connect(this.ctx.destination);
    proc.onaudioprocess = (e) => this._process(e.inputBuffer.getChannelData(0));
    this.sr = this.ctx.sampleRate;
  }

  setEnabled(v) {
    this.enabled = v;
    if (!v && this.speaking) this._endUtterance();
  }

  _process(frame) {
    if (!this.enabled) return;
    let sum = 0;
    for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
    const rms = Math.sqrt(sum / frame.length);
    const frameMs = (frame.length / this.sr) * 1000;

    if (rms > this.THRESH) {
      if (!this.speaking) { this.speaking = true; this.onUtteranceStart?.(); }
      this.silenceMs = 0;
      const pcm = floatToPcm16(downsample(frame, this.sr));
      this.onChunk?.(pcm);
    } else if (this.speaking) {
      this.silenceMs += frameMs;
      const pcm = floatToPcm16(downsample(frame, this.sr));
      this.onChunk?.(pcm); // добираем хвост тишины
      if (this.silenceMs > this.SILENCE_LIMIT) this._endUtterance();
    }
  }

  _endUtterance() {
    this.speaking = false;
    this.silenceMs = 0;
    this.onUtteranceEnd?.();
  }
}

// ── Потоковый плеер PCM16 @16k с частотным анализом (ТЗ §16) ─────────
// Аудио проходит через AnalyserNode → визуал синхронизирован именно с тем,
// что звучит из колонок (RMS + низкие/средние/высокие частоты).
export class PcmPlayer {
  constructor(onAmp) {
    this.onAmp = onAmp;
    this.ctx = new AudioContext({ sampleRate: TARGET_SR });
    this.nextTime = 0;

    this.gain = this.ctx.createGain();
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 512;
    this.analyser.smoothingTimeConstant = 0.6;
    this.gain.connect(this.analyser);
    this.analyser.connect(this.ctx.destination);

    this.freq = new Uint8Array(this.analyser.frequencyBinCount);
    this.time = new Uint8Array(this.analyser.fftSize);
  }

  resume() { return this.ctx.resume(); }

  // bytes: ArrayBuffer с PCM16 LE mono @16k
  push(bytes) {
    const pcm = new Int16Array(bytes);
    if (!pcm.length) return;
    const f32 = new Float32Array(pcm.length);
    let peak = 0;
    for (let i = 0; i < pcm.length; i++) {
      f32[i] = pcm[i] / 0x8000;
      peak = Math.max(peak, Math.abs(f32[i]));
    }
    this.onAmp?.(peak);

    const buf = this.ctx.createBuffer(1, f32.length, TARGET_SR);
    buf.copyToChannel(f32, 0);
    const node = this.ctx.createBufferSource();
    node.buffer = buf;
    node.connect(this.gain);

    const now = this.ctx.currentTime;
    if (this.nextTime < now) this.nextTime = now + 0.02;
    node.start(this.nextTime);
    this.nextTime += buf.duration;
  }

  // Текущие уровни для сферы. Вызывать каждый кадр во время речи.
  // Возвращает {rms, low, mid, high} в диапазоне ~0..1.
  getLevels() {
    const a = this.analyser;
    a.getByteFrequencyData(this.freq);
    a.getByteTimeDomainData(this.time);

    // RMS по временной области
    let sum = 0;
    for (let i = 0; i < this.time.length; i++) {
      const v = (this.time[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.min(1, Math.sqrt(sum / this.time.length) * 2.2);

    // частотные полосы (16 kHz → Найквист 8 kHz)
    const n = this.freq.length;
    const band = (a0, a1) => {
      let s = 0, c = 0;
      const i0 = Math.floor(a0 * n), i1 = Math.floor(a1 * n);
      for (let i = i0; i < i1; i++) { s += this.freq[i]; c++; }
      return c ? Math.min(1, s / c / 200) : 0;
    };
    return {
      rms,
      low: band(0.0, 0.12),
      mid: band(0.12, 0.4),
      high: band(0.4, 1.0),
    };
  }
}
