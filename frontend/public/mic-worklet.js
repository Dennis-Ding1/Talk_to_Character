// AudioWorklet: mic Float32 at the device rate (`sampleRate` global, often 44.1/48 kHz)
// -> 24 kHz PCM16, posted to the main thread in ~100 ms chunks.
// A simple low-pass runs before downsampling so higher frequencies don't fold back into speech.
// The main thread can send "flush" to get the last partial chunk right away (end of a turn).
const TARGET = 24000;

class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / TARGET; // input samples per output sample
    this.pos = 0; // fractional read position into the incoming stream
    this.prev = 0; // last (filtered) sample of the previous block
    this.lp = 0; // one-pole low-pass state
    // cutoff ~10 kHz (just under the 12 kHz Nyquist of the 24 kHz output)
    this.alpha = this.ratio > 1 ? 1 - Math.exp((-2 * Math.PI * 10000) / sampleRate) : 1;
    this.buf = new Int16Array(TARGET / 10);
    this.len = 0;
    this.port.onmessage = (e) => {
      if (e.data === "flush" && this.len > 0) {
        this.port.postMessage(this.buf.slice(0, this.len).buffer);
        this.len = 0;
      }
    };
  }

  process(inputs) {
    const raw = inputs[0] && inputs[0][0];
    if (!raw) return true;
    const ch = new Float32Array(raw.length);
    for (let k = 0; k < raw.length; k++) ch[k] = this.lp += this.alpha * (raw[k] - this.lp);
    // linear interpolation resampler
    while (this.pos < ch.length) {
      const i = Math.floor(this.pos);
      const frac = this.pos - i;
      const a = i === 0 ? this.prev : ch[i - 1];
      const b = ch[i];
      const s = Math.max(-1, Math.min(1, a + (b - a) * frac));
      this.buf[this.len++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.len === this.buf.length) {
        this.port.postMessage(this.buf.buffer.slice(0));
        this.len = 0;
      }
      this.pos += this.ratio;
    }
    this.pos -= ch.length;
    this.prev = ch[ch.length - 1];
    return true;
  }
}
registerProcessor("mic-processor", MicProcessor);
