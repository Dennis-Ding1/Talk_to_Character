import { bytesToBase64 } from "./pcm";

/** Captures the microphone as 24 kHz PCM16 and calls onChunk with base64 (~100 ms each).
 *  Uses the device's native sample rate and resamples in the worklet (forcing a 24 kHz
 *  AudioContext breaks in some browsers). */
export class Mic {
  private ctx?: AudioContext;
  private stream?: MediaStream;
  private node?: AudioWorkletNode;
  /** Seconds of audio captured since start(). */
  seconds = 0;

  async start(onChunk: (b64: string) => void) {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.ctx = new AudioContext();
    await this.ctx.audioWorklet.addModule("/mic-worklet.js");
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "mic-processor");
    this.seconds = 0;
    this.node.port.onmessage = (e: MessageEvent<ArrayBuffer>) => {
      this.seconds += e.data.byteLength / 2 / 24000;
      onChunk(bytesToBase64(new Uint8Array(e.data)));
    };
    src.connect(this.node);
  }

  stop() {
    this.node?.port.close();
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close();
    this.ctx = this.stream = this.node = undefined;
  }
}
