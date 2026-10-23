import { base64ToBytes } from "./pcm";

/** Gapless playback of streamed 24 kHz PCM16 chunks, with instant stop for barge-in. */
export class PcmPlayer {
  private ctx = new AudioContext({ sampleRate: 24000 });
  private playHead = 0;
  private sources: AudioBufferSourceNode[] = [];
  /** Raw PCM of the current reply (for driving the avatar after the fact). */
  recorded: Uint8Array[] = [];

  push(b64: string) {
    const bytes = base64ToBytes(b64);
    this.recorded.push(bytes);
    const samples = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
    const buf = this.ctx.createBuffer(1, samples.length, 24000);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < samples.length; i++) ch[i] = samples[i] / 0x8000;

    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.ctx.destination);
    const now = this.ctx.currentTime;
    this.playHead = Math.max(this.playHead, now + 0.03);
    src.start(this.playHead);
    this.playHead += buf.duration;
    this.sources.push(src);
    src.onended = () => (this.sources = this.sources.filter((s) => s !== src));
  }

  get playing() {
    return this.sources.length > 0;
  }

  stop() {
    this.sources.forEach((s) => s.stop());
    this.sources = [];
    this.playHead = 0;
  }

  takeRecording(): Uint8Array {
    const total = this.recorded.reduce((n, b) => n + b.length, 0);
    const out = new Uint8Array(total);
    let o = 0;
    for (const b of this.recorded) {
      out.set(b, o);
      o += b.length;
    }
    this.recorded = [];
    return out;
  }

  async resume() {
    if (this.ctx.state === "suspended") await this.ctx.resume();
  }
}
