import { bytesToBase64 } from "./pcm";

const PRE_ROLL_S = 0.5; // audio kept from just before the button press (people start talking at once)
const TAIL_MS = 250; // keep recording briefly after the stop press (people press stop on the last word)
const GATE_HOLD = 3; // ~300 ms of loud audio while the character talks = the user cutting in
const GATE_RING = 7; // ~700 ms kept from before the cut-in is confirmed (so its first words are heard)

/** Captures the microphone as 24 kHz PCM16 (~100 ms base64 chunks) for push-to-talk.
 *  The microphone stays open for the whole conversation once opened, so a press doesn't pay the
 *  few hundred ms it takes to open it (which cut off the first words). While not recording, the
 *  last PRE_ROLL_S seconds are kept and sent at the start of the next recording.
 *  Uses the device's native sample rate and resamples in the worklet (forcing a 24 kHz
 *  AudioContext breaks in some browsers). */
export class Mic {
  private ctx?: AudioContext;
  private stream?: MediaStream;
  private node?: AudioWorkletNode;
  private opening?: Promise<void>;
  private onChunk?: (b64: string) => void;
  private preRoll: ArrayBuffer[] = [];
  /** Echo guard for hands-free use: while it returns > 0 (the character is talking), audio is held
   *  back unless it stays louder than that RMS (0..1) for a moment, so the character's own voice
   *  from the speakers doesn't count as the user talking (and interrupt them). */
  gate?: () => number;
  private gateOpen = false; // the user is talking over the character: let everything through
  private recent: ArrayBuffer[] = []; // last chunks held while the character talks
  private loudRun = 0; // loud chunks in a row while the character talks
  /** Seconds of audio captured since start(). */
  seconds = 0;

  get isOpen() {
    return !!this.node;
  }

  /** Open the microphone (asks for permission the first time). Safe to call repeatedly. */
  open(): Promise<void> {
    if (this.node) return Promise.resolve();
    this.opening ??= (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        const ctx = new AudioContext();
        await ctx.audioWorklet.addModule("/mic-worklet.js");
        const node = new AudioWorkletNode(ctx, "mic-processor");
        node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => this.receive(e.data);
        ctx.createMediaStreamSource(stream).connect(node);
        this.stream = stream;
        this.ctx = ctx;
        this.node = node;
      } finally {
        this.opening = undefined;
      }
    })();
    return this.opening;
  }

  private receive(buf: ArrayBuffer) {
    if (this.onChunk) {
      this.seconds += buf.byteLength / 2 / 24000;
      const min = this.gate?.() ?? 0;
      if (min <= 0 || this.gateOpen) {
        if (min <= 0) {
          this.gateOpen = false;
          this.recent = []; // held audio from while the character talked: their voice, not the user
          this.loudRun = 0;
        }
        this.onChunk(bytesToBase64(new Uint8Array(buf)));
        return;
      }
      // While the character talks, nothing is sent: only sustained loud speech (GATE_HOLD chunks in
      // a row) counts as the user cutting in; short bursts are usually the character's own voice from
      // the speakers. The last GATE_RING chunks are kept, so when the user does cut in, their first
      // (quieter) words go out too instead of being lost.
      this.recent.push(buf);
      if (this.recent.length > GATE_RING) this.recent.shift();
      this.loudRun = rms(buf) >= min ? this.loudRun + 1 : 0;
      if (this.loudRun >= GATE_HOLD) {
        this.gateOpen = true;
        for (const b of this.recent) this.onChunk(bytesToBase64(new Uint8Array(b)));
        this.recent = [];
      }
      return;
    }
    this.preRoll.push(buf);
    let total = this.preRoll.reduce((n, b) => n + b.byteLength, 0);
    while (this.preRoll.length > 1 && total - this.preRoll[0].byteLength >= PRE_ROLL_S * 48000) {
      total -= this.preRoll.shift()!.byteLength;
    }
  }

  /** Start sending audio (opens the microphone if needed). `preRoll: false` skips the audio from
   *  before the press, e.g. when the character was still talking through the speakers. */
  async start(onChunk: (b64: string) => void, { preRoll = true } = {}) {
    await this.open();
    if (this.ctx?.state === "suspended") await this.ctx.resume();
    this.seconds = 0;
    const before = preRoll ? this.preRoll : [];
    this.preRoll = [];
    this.onChunk = onChunk;
    for (const b of before) onChunk(bytesToBase64(new Uint8Array(b)));
  }

  /** Stop sending; resolves once the last audio (a short tail plus the partial chunk) is out.
   *  The microphone stays open for the next press. */
  async stop(): Promise<void> {
    if (!this.onChunk) return;
    await new Promise((r) => window.setTimeout(r, TAIL_MS));
    this.node?.port.postMessage("flush");
    await new Promise((r) => window.setTimeout(r, 30)); // let the flushed chunk arrive
    this.onChunk = undefined;
  }

  /** Release the microphone (end of the conversation). */
  close() {
    this.onChunk = undefined;
    this.preRoll = [];
    this.node?.port.close();
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close();
    this.ctx = this.stream = this.node = undefined;
  }
}

function rms(buf: ArrayBuffer) {
  const v = new Int16Array(buf);
  let sum = 0;
  for (let i = 0; i < v.length; i++) sum += v[i] * v[i];
  return Math.sqrt(sum / Math.max(1, v.length)) / 0x8000;
}
