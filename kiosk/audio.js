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
  constructor({ onUtteranceStart, onChunk, onUtteranceEnd, onUtteranceCancel }) {
    this.onUtteranceStart = onUtteranceStart;
    this.onChunk = onChunk;          // (Int16Array) во время речи
    this.onUtteranceEnd = onUtteranceEnd;
    this.onUtteranceCancel = onUtteranceCancel; // фраза слишком короткая
    this.speaking = false;
    this.silenceMs = 0;
    this.speechMs = 0;               // сколько реальной речи накопилось
    this.enabled = false;            // «слушаем ли сейчас пациента»
    this.SILENCE_LIMIT = 800;        // мс тишины = конец фразы
    this.MIN_SPEECH_MS = 400;        // короче — шорох, не отправляем в STT
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
      if (!this.speaking) { this.speaking = true; this.speechMs = 0; this.onUtteranceStart?.(); }
      this.silenceMs = 0;
      this.speechMs += frameMs;
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
    const tooShort = this.speechMs < this.MIN_SPEECH_MS;
    this.speaking = false;
    this.silenceMs = 0;
    this.speechMs = 0;
    if (tooShort) this.onUtteranceCancel?.();
    else this.onUtteranceEnd?.();
  }
}

// ── Потоковый плеер PCM16 @16k с колбэком амплитуды ─────────────────
export class PcmPlayer {
  constructor(onAmp) {
    this.onAmp = onAmp;
    this.ctx = new AudioContext({ sampleRate: TARGET_SR });
    this.nextTime = 0;
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
    node.connect(this.ctx.destination);

    const now = this.ctx.currentTime;
    if (this.nextTime < now) this.nextTime = now + 0.02;
    node.start(this.nextTime);
    this.nextTime += buf.duration;
  }
}
