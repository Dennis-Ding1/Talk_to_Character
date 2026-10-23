// AudioWorklet: converts mic Float32 frames to PCM16 and posts ~100 ms chunks to the main thread.
// Runs in an AudioContext created at 24 kHz, so no resampling is needed here.
class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Int16Array(2400); // 100 ms @ 24 kHz
    this.len = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      const s = Math.max(-1, Math.min(1, ch[i]));
      this.buf[this.len++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.len === this.buf.length) {
        this.port.postMessage(this.buf.buffer.slice(0));
        this.len = 0;
      }
    }
    return true;
  }
}
registerProcessor("mic-processor", MicProcessor);
