import { base64ToBytes } from "./pcm";

/** Gapless playback of streamed 24 kHz PCM16 mono chunks, with instant stop for barge-in. */
export class PcmPlayer {
  private ctx = new AudioContext({ sampleRate: 24000 });
  private playHead = 0;
  private sources: AudioBufferSourceNode[] = [];
  private carry: number | null = null; // odd trailing byte from the previous network chunk

  push(b64: string) {
    this.pushBytes(base64ToBytes(b64));
  }

  /** Raw PCM16 little-endian bytes, as they arrive from a stream (any chunk size). */
  pushBytes(chunk: Uint8Array) {
    let bytes = chunk;
    if (this.carry !== null) {
      bytes = new Uint8Array(chunk.length + 1);
      bytes[0] = this.carry;
      bytes.set(chunk, 1);
      this.carry = null;
    }
    if (bytes.length % 2) {
      this.carry = bytes[bytes.length - 1];
      bytes = bytes.subarray(0, bytes.length - 1);
    }
    if (!bytes.length) return;
    const n = bytes.length / 2;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const buf = this.ctx.createBuffer(1, n, 24000);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < n; i++) ch[i] = view.getInt16(i * 2, true) / 0x8000;

    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(this.ctx.destination);
    const now = this.ctx.currentTime;
    // starting fresh (nothing queued): a small lead absorbs network jitter between chunks
    if (this.playHead < now) this.playHead = now + 0.12;
    src.start(this.playHead);
    this.playHead += buf.duration;
    this.sources.push(src);
    src.onended = () => (this.sources = this.sources.filter((s) => s !== src));
  }

  get playing() {
    return this.sources.length > 0;
  }

  stop() {
    this.sources.forEach((s) => {
      try {
        s.stop();
      } catch {
        /* already stopped */
      }
    });
    this.sources = [];
    this.playHead = 0;
    this.carry = null;
  }

  async resume() {
    if (this.ctx.state === "suspended") await this.ctx.resume();
  }
}
