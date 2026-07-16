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
    if (!v && this.speaking) {
      // Принудительное выключение посреди фразы — обрывок не отправляем
      this.speaking = false;
      this.silenceMs = 0;
      this.speechMs = 0;
      this.onUtteranceCancel?.();
    }
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

// ── Потоковый плеер PCM16 @16k с анализом РЕАЛЬНОГО звука ───────────
// Весь звук идёт через AnalyserNode, и амплитуда/спектр снимаются с того,
// что звучит из динамика ПРЯМО СЕЙЧАС (а не в момент прихода чанка по
// сети). Визуализация синхронна с голосом всю фразу, а не первые секунды.
const BAND_EDGES = [100, 200, 400, 700, 1100, 1700, 2600, 3900, 5500]; // Гц

export class PcmPlayer {
  constructor() {
    this.ctx = new AudioContext({ sampleRate: TARGET_SR });
    this.nextTime = 0;

    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 512;                  // бин = 31.25 Гц @16k
    this.analyser.smoothingTimeConstant = 0.55;
    this.analyser.connect(this.ctx.destination);

    this.freqData = new Uint8Array(this.analyser.frequencyBinCount);
    this.timeData = new Uint8Array(this.analyser.fftSize);
    this.bands = new Float32Array(BAND_EDGES.length - 1);

    // границы полос в бинах FFT
    const binHz = TARGET_SR / this.analyser.fftSize;
    this.binEdges = BAND_EDGES.map((f) => Math.max(0,
      Math.min(this.analyser.frequencyBinCount - 1, Math.round(f / binHz))));
  }

  resume() { return this.ctx.resume(); }

  // bytes: ArrayBuffer с PCM16 LE mono @16k
  push(bytes) {
    const pcm = new Int16Array(bytes);
    if (!pcm.length) return;
    const f32 = new Float32Array(pcm.length);
    for (let i = 0; i < pcm.length; i++) f32[i] = pcm[i] / 0x8000;

    const buf = this.ctx.createBuffer(1, f32.length, TARGET_SR);
    buf.copyToChannel(f32, 0);
    const node = this.ctx.createBufferSource();
    node.buffer = buf;
    node.connect(this.analyser);   // → анализатор → динамик

    const now = this.ctx.currentTime;
    if (this.nextTime < now) this.nextTime = now + 0.02;
    node.start(this.nextTime);
    this.nextTime += buf.duration;
  }

  // Снять текущие амплитуду и 8 полос с воспроизводимого звука.
  // Вызывается визуализатором каждый кадр.
  sample() {
    this.analyser.getByteTimeDomainData(this.timeData);
    let peak = 0;
    for (let i = 0; i < this.timeData.length; i++) {
      peak = Math.max(peak, Math.abs(this.timeData[i] - 128));
    }
    const amp = peak / 128;

    this.analyser.getByteFrequencyData(this.freqData);
    for (let b = 0; b < this.bands.length; b++) {
      const from = this.binEdges[b], to = Math.max(from + 1, this.binEdges[b + 1]);
      let sum = 0;
      for (let i = from; i < to; i++) sum += this.freqData[i];
      const avg = sum / (to - from) / 255;
      // высокие частоты тише — компенсируем усилением
      this.bands[b] = Math.min(1, avg * (1.1 + b * 0.35));
    }
    return { amp, bands: this.bands };
  }
}
