import { forwardRef } from "react";

interface Props {
  src: string;
  subtitlesSrc?: string;
  onPause: (t: number) => void;
  onPlay: () => void;
}

/** Plain <video>. Pausing opens the character picker at the current time. */
export const VideoPlayer = forwardRef<HTMLVideoElement, Props>(function VideoPlayer(
  { src, onPause, onPlay },
  ref,
) {
  // TODO: SRT -> WebVTT conversion to show subtitles via <track>.
  return (
    <video
      ref={ref}
      className="movie"
      src={src}
      controls
      onPause={(e) => {
        const v = e.currentTarget;
        if (!v.ended && !v.seeking) onPause(v.currentTime);
      }}
      onPlay={onPlay}
    />
  );
});
