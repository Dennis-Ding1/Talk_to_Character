import { forwardRef } from "react";

interface Props {
  src: string;
  onPlay: () => void;
  onPause?: () => void;
  onTime?: (t: number, duration: number) => void;
}

/** The film itself. No browser controls: play/pause and the timeline are drawn by the page (Transport). */
export const VideoPlayer = forwardRef<HTMLVideoElement, Props>(function VideoPlayer({ src, onPlay, onPause, onTime }, ref) {
  // TODO: SRT -> WebVTT conversion to show subtitles via <track>.
  return (
    <video
      ref={ref}
      className="movie"
      src={src}
      playsInline
      onPlay={onPlay}
      onPause={onPause}
      onTimeUpdate={(e) => onTime?.(e.currentTarget.currentTime, e.currentTarget.duration)}
      onLoadedMetadata={(e) => onTime?.(e.currentTarget.currentTime, e.currentTarget.duration)}
      onClick={(e) => (e.currentTarget.paused ? void e.currentTarget.play() : e.currentTarget.pause())}
    />
  );
});
