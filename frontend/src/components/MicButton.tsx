interface Props {
  listening: boolean;
  disabled?: boolean;
  onStart: () => void;
  onStop: () => void;
}

/** Toggle mic. Turn-taking is automatic (Higgs semantic VAD); speaking over the character interrupts it. */
export function MicButton({ listening, disabled, onStart, onStop }: Props) {
  return (
    <button
      className={`mic ${listening ? "on" : ""}`}
      disabled={disabled}
      onClick={listening ? onStop : onStart}
      aria-pressed={listening}
    >
      {listening ? "● Listening — tap to stop" : "🎙 Talk"}
    </button>
  );
}
