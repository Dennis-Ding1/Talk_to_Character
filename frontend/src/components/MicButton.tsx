import { Icon } from "./Icon";

interface Props {
  listening: boolean;
  /** hands-free: the button mutes / unmutes an always-on mic instead of recording a turn */
  handsFree?: boolean;
  disabled?: boolean;
  onStart: () => void;
  onStop: () => void;
}

/** Push-to-talk: tap to start recording (interrupts the character), tap again to send.
 *  Hands-free: the mic is on; tap to mute, tap again to unmute. */
export function MicButton({ listening, handsFree, disabled, onStart, onStop }: Props) {
  if (handsFree) {
    return (
      <button
        type="button"
        className={`mic ${listening ? "on live" : ""}`}
        disabled={disabled}
        onClick={listening ? onStop : onStart}
        aria-pressed={listening}
        aria-label={listening ? "Mute the mic" : "Unmute the mic"}
        title={listening ? "Mic on. Tap to mute" : "Mic off. Tap to unmute"}
      >
        <Icon name={listening ? "mic" : "mic-off"} size={22} />
      </button>
    );
  }
  return (
    <button
      type="button"
      className={`mic ${listening ? "on" : ""}`}
      disabled={disabled}
      onClick={listening ? onStop : onStart}
      aria-pressed={listening}
      aria-label={listening ? "Stop recording and send" : "Speak"}
      title={listening ? "Tap to send" : "Tap to speak"}
    >
      <Icon name={listening ? "stop" : "mic"} size={22} />
    </button>
  );
}
