import { forwardRef } from "react";

interface Props {
  src: string;
  onPlay: () => void;
}

/** Plain <video>. Pausing does nothing special; talking starts from the "Talk" button. */
export const VideoPlayer = forwardRef<HTMLVideoElement, Props>(function VideoPlayer({ src, onPlay }, ref) {
  // TODO: SRT -> WebVTT conversion to show subtitles via <track>.
  return <video ref={ref} className="movie" src={src} controls onPlay={onPlay} />;
});
