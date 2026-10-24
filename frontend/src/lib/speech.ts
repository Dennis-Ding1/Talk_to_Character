import type { PcmPlayer } from "./audio/pcm-player";

interface Handlers {
  /** POST one sentence to /api/speak (spoiler check + cloned-voice TTS); returns the PCM stream */
  request: (text: string, signal: AbortSignal) => Promise<Response>;
  /** the text actually spoken (after the spoiler check), at the moment its audio starts sounding */
  onSpoken: (text: string, rewritten: boolean, tag: string) => void;
  onStart: () => void;
  /** all queued sentences have finished playing */
  onIdle: () => void;
}

/**
 * Speaks a reply sentence by sentence. Every sentence is sent to the backend as soon as it is
 * written (requests run in parallel, so the next one is ready while the current one plays) and
 * played strictly in order through one gapless PCM player.
 */
export class SpeechQueue {
  private items: { text: string; res?: Promise<Response>; abort: AbortController; tag: string }[] = [];
  private static readonly MAX_IN_FLIGHT = 2; // the sentence playing + the next one
  private running = false;
  private gen = 0;
  /** sentences whose words are waiting for their audio to actually start */
  private waitingToShow = 0;

  constructor(
    private player: PcmPlayer,
    private h: Handlers,
  ) {}

  /** tag: which reply this sentence belongs to (passed back in onSpoken) */
  enqueue(text: string, tag: string) {
    this.items.push({ text, abort: new AbortController(), tag });
    this.fetchAhead();
    void this.run();
  }

  /** Request at most MAX_IN_FLIGHT sentences ahead: parallel synthesis slows each request down, so
   *  the first sentence (the one the user is waiting for) gets the bandwidth to itself. */
  private fetchAhead() {
    for (const it of this.items.slice(0, SpeechQueue.MAX_IN_FLIGHT)) {
      if (!it.res) {
        it.res = this.h.request(it.text, it.abort.signal);
        it.res.catch(() => {});
      }
    }
  }

  get busy() {
    return this.running || this.items.length > 0 || this.player.playing || this.waitingToShow > 0;
  }

  /** Interrupt: drop everything, silence now. */
  stop() {
    this.gen++;
    this.waitingToShow = 0;
    for (const it of this.items) it.abort.abort();
    this.items = [];
    this.running = false;
    this.player.stop();
  }

  private async run() {
    if (this.running) return;
    this.running = true;
    const gen = this.gen;
    let started = false;
    while (this.items.length && gen === this.gen) {
      const it = this.items[0];
      this.fetchAhead();
      try {
        const res = await it.res!;
        if (gen !== this.gen) break;
        if (res.ok && res.body) {
          const spoken = decodeURIComponent(res.headers.get("X-Spoken-Text") ?? "");
          const rewritten = res.headers.get("X-Spoiler-Rewritten") === "1";
          // subtitles: the words appear when this sentence's audio really starts, not when it arrives
          // (the previous sentence may still be playing)
          let shown = false;
          const show = (delayMs: number) => {
            if (shown) return;
            shown = true;
            this.waitingToShow++;
            window.setTimeout(() => {
              if (gen !== this.gen) return;
              this.waitingToShow--;
              this.h.onSpoken(spoken, rewritten, it.tag);
              if (!started) {
                started = true;
                this.h.onStart();
              }
            }, delayMs);
          };
          const reader = res.body.getReader();
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            if (gen !== this.gen) {
              void reader.cancel();
              break;
            }
            const startsAt = this.player.pushBytes(value);
            if (startsAt !== null) show(this.player.msUntil(startsAt));
          }
          // no audio came back (TTS failed): still show the words, once whatever is playing ends
          if (gen === this.gen) show(this.player.msUntilDone);
        }
      } catch {
        // aborted or failed: skip this sentence
      }
      if (gen === this.gen) this.items.shift();
    }
    if (gen !== this.gen) return;
    this.running = false;
    // wait for the audio already scheduled to finish before saying we're idle
    while ((this.player.playing || this.waitingToShow > 0) && gen === this.gen && !this.items.length) {
      await new Promise((r) => setTimeout(r, 150));
    }
    if (gen === this.gen && !this.items.length && !this.running) this.h.onIdle();
  }
}
