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
    >
      {listening ? "● Recording — tap to send" : "🎙 Speak"}
    </button>
  );
}
