/**
 * Splits a reply that arrives as streamed text deltas into sentences, so each one can be
 * spoiler-checked and spoken while the rest of the reply is still being written.
 *
 * The first chunk goes out as soon as one sentence is complete (fast first audio); later chunks
 * gather sentences up to ~minLater characters (fewer, more natural TTS segments).
 */
const BOUNDARY = /[^.!?。！？…]*[.!?。！？…]+["'”’)\]]*\s*/g;

export class SentenceChunker {
  private buf = "";
  private emitted = 0;

  constructor(
    private onChunk: (text: string) => void,
    private minFirst = 10,
    private minLater = 60,
  ) {}

  push(delta: string) {
    this.buf += delta;
    this.drain(false);
  }

  /** End of the reply: emit whatever is left. */
  flush() {
    this.drain(true);
    this.buf = "";
  }

  private drain(final: boolean) {
    for (;;) {
      const min = this.emitted === 0 ? this.minFirst : this.minLater;
      let end = 0;
      BOUNDARY.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = BOUNDARY.exec(this.buf)) && m[0].length > 0) {
        end = BOUNDARY.lastIndex;
        if (end >= min) break;
      }
      if (end >= min || (final && this.buf.trim())) {
        const cut = end >= min ? end : this.buf.length;
        const chunk = this.buf.slice(0, cut).trim();
        this.buf = this.buf.slice(cut);
        if (chunk) {
          this.emitted++;
          this.onChunk(chunk);
        }
        if (end >= min || (final && this.buf.trim())) continue;
      }
      return;
    }
  }
}
