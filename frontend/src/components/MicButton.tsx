import { Icon } from "./Icon";

interface Props {
  listening: boolean;
  disabled?: boolean;
  onStart: () => void;
  onStop: () => void;
}

/** Push-to-talk: tap to start recording (interrupts the character), tap again to send. */
export function MicButton({ listening, disabled, onStart, onStop }: Props) {
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
