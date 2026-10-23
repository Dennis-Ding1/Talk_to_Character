// AudioWorklet: mic Float32 at the device rate (`sampleRate` global, often 44.1/48 kHz)
// -> 24 kHz PCM16, posted to the main thread in ~100 ms chunks.
const TARGET = 24000;

class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / TARGET; // input samples per output sample
    this.pos = 0; // fractional read position into the incoming stream
    this.prev = 0; // last sample of the previous block (for interpolation across blocks)
    this.buf = new Int16Array(TARGET / 10);
    this.len = 0;
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
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
