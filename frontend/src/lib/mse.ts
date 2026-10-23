/**
 * Plays a fragmented-MP4 HTTP stream (Higgs Avatar /v1/videos/stream) in a <video> element
 * as it arrives, using Media Source Extensions. Falls back to "download then play" if the
 * codec string isn't supported.
 *
 * TODO(avatar owner): confirm the actual codecs Higgs returns (inspect the moov box or ask
 * Boson) and put the exact string first in CANDIDATE_TYPES.
 */
const CANDIDATE_TYPES = [
  'video/mp4; codecs="avc1.64001F, mp4a.40.2"',
  'video/mp4; codecs="avc1.42E01E, mp4a.40.2"',
  'video/mp4; codecs="avc1.4D401F, mp4a.40.2"',
];

export async function playFmp4Stream(video: HTMLVideoElement, res: Response): Promise<void> {
  if (!res.ok || !res.body) throw new Error(`avatar stream failed: ${res.status} ${await res.text()}`);
  const type = window.MediaSource && CANDIDATE_TYPES.find((t) => MediaSource.isTypeSupported(t));
  if (!type) return playAsBlob(video, res);

  const ms = new MediaSource();
  video.src = URL.createObjectURL(ms);
  await new Promise<void>((r) => ms.addEventListener("sourceopen", () => r(), { once: true }));
  const sb = ms.addSourceBuffer(type);
  sb.mode = "sequence";

  const reader = res.body.getReader();
  let started = false;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (sb.updating) await new Promise((r) => sb.addEventListener("updateend", r, { once: true }));
    sb.appendBuffer(value);
    await new Promise((r) => sb.addEventListener("updateend", r, { once: true }));
    if (!started && sb.buffered.length && sb.buffered.end(0) > 0.3) {
      started = true;
      void video.play();
    }
  }
  if (ms.readyState === "open") ms.endOfStream();
  if (!started) void video.play();
  await new Promise((r) => video.addEventListener("ended", r, { once: true }));
}

async function playAsBlob(video: HTMLVideoElement, res: Response) {
  const blob = await res.blob();
  video.src = URL.createObjectURL(blob);
  await video.play();
  await new Promise((r) => video.addEventListener("ended", r, { once: true }));
}
