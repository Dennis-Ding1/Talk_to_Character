/**
 * Plays a fragmented-MP4 HTTP stream (Higgs Avatar /v1/videos/stream) in a <video> element
 * as it arrives, using Media Source Extensions. Falls back to "download then play" if the
 * codec string isn't supported.
 *
 * Measured from a real Higgs Avatar stream: H.264 High (avc1.64001E) 640x640 24fps + AAC-LC 24 kHz,
 * ftyp/moov then moof/mdat fragments. After a ~6 s start-up the render runs at ~0.99x real time with
 * ~1 s of jitter, so we buffer 3 s before starting; with less the playback catches up and stutters.
 */
const CANDIDATE_TYPES = [
  'video/mp4; codecs="avc1.64001E, mp4a.40.2"',
  'video/mp4; codecs="avc1.64001F, mp4a.40.2"',
  'video/mp4; codecs="avc1.42E01E, mp4a.40.2"',
  'video/mp4; codecs="avc1.4D401F, mp4a.40.2"',
];

export interface PlayOptions {
  /** called once, when the first frame is actually on screen (fade the video in now) */
  onStart?: () => void;
  signal?: AbortSignal;
  /** stop downloading (frees Boson's render slot for the next reply) but keep playing what is
   *  already buffered; the video then ends normally */
  finish?: AbortSignal;
  /** seconds of video to buffer before starting playback */
  startBuffer?: number;
}

export async function playFmp4Stream(video: HTMLVideoElement, res: Response, opts: PlayOptions = {}): Promise<void> {
  if (!res.ok || !res.body) throw new Error(`avatar stream failed: ${res.status} ${await res.text()}`);
  const startBuffer = opts.startBuffer ?? 3.0;
  if (opts.onStart) video.addEventListener("playing", () => opts.onStart?.(), { once: true });
  const type = window.MediaSource && CANDIDATE_TYPES.find((t) => MediaSource.isTypeSupported(t));
  if (!type) return playAsBlob(video, res, opts.signal);

  const ms = new MediaSource();
  const msUrl = URL.createObjectURL(ms);
  video.src = msUrl;
  await new Promise<void>((r) => ms.addEventListener("sourceopen", () => r(), { once: true }));
  const sb = ms.addSourceBuffer(type);
  sb.mode = "sequence";

  const reader = res.body.getReader();
  opts.finish?.addEventListener("abort", () => reader.cancel().catch(() => {}), { once: true });
  const ended = new Promise<void>((r) => video.addEventListener("ended", () => r(), { once: true }));
  const aborted = new Promise<void>((r) => opts.signal?.addEventListener("abort", () => r(), { once: true }));
  let started = false;
  const start = () => {
    if (started) return;
    started = true;
    video.play().catch(() => {
      video.muted = true; // autoplay with sound refused: at least show the lips moving
      void video.play();
    });
  };
  try {
    for (;;) {
      if (opts.signal?.aborted) return;
      if (opts.finish?.aborted) break;
      const { done, value } = await reader.read();
      if (done || opts.finish?.aborted) break;
      if (sb.updating) await new Promise((r) => sb.addEventListener("updateend", r, { once: true }));
      sb.appendBuffer(value);
      await new Promise((r) => sb.addEventListener("updateend", r, { once: true }));
      if (sb.buffered.length && sb.buffered.end(0) >= startBuffer) start();
    }
    if (sb.updating) await new Promise((r) => sb.addEventListener("updateend", r, { once: true }));
    if (ms.readyState === "open") ms.endOfStream();
    start();
    await Promise.race([ended, aborted]);
  } finally {
    reader.cancel().catch(() => {});
    window.setTimeout(() => URL.revokeObjectURL(msUrl), 1000);
  }
}

async function playAsBlob(video: HTMLVideoElement, res: Response, signal?: AbortSignal) {
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  video.src = url;
  await video.play();
  await Promise.race([
    new Promise((r) => video.addEventListener("ended", r, { once: true })),
    new Promise((r) => signal?.addEventListener("abort", r, { once: true })),
  ]);
  URL.revokeObjectURL(url);
}
