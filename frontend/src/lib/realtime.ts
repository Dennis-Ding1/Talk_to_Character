/**
 * Browser client for Higgs Realtime (wss://api.boson.ai/v1/realtime).
 * Auth: ephemeral key from our backend, passed as the `bai-client-secret.<key>` subprotocol.
 * Event names: https://docs.boson.ai/api-reference/realtime/server-events
 */

export interface RealtimeHandlers {
  onUserTranscript?: (itemId: string, text: string) => void;
  onAssistantDelta?: (itemId: string, delta: string) => void; // transcript (audio mode) or text (text mode)
  onAssistantDone?: (itemId: string, text: string) => void;
  onAudioDelta?: (b64: string) => void;
  onSpeechStarted?: () => void; // user started talking -> barge-in
  onResponseDone?: (status: string) => void;
  onToolCall?: (name: string, args: unknown) => Promise<string>;
  onError?: (err: unknown) => void;
  onClose?: () => void;
}

type ServerEvent = { type: string; [k: string]: any };

export class RealtimeSession {
  private ws?: WebSocket;
  private textBuf = new Map<string, string>();

  constructor(private h: RealtimeHandlers) {}

  connect(url: string, clientSecret: string, session: Record<string, unknown>, history: unknown[] = []) {
    return new Promise<void>((resolve, reject) => {
      const ws = new WebSocket(url, ["realtime", `bai-client-secret.${clientSecret}`]);
      this.ws = ws;
      ws.onopen = () => {
        this.send({ type: "session.update", session });
        for (const item of history) this.send({ type: "conversation.item.create", item });
        resolve();
      };
      ws.onerror = (e) => {
        this.h.onError?.(e);
        reject(e);
      };
      ws.onclose = () => this.h.onClose?.();
      ws.onmessage = (m) => void this.handle(JSON.parse(m.data as string));
    });
  }

  send(ev: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(ev));
  }

  appendAudio(b64: string) {
    this.send({ type: "input_audio_buffer.append", audio: b64 });
  }

  sendText(text: string) {
    this.send({
      type: "conversation.item.create",
      item: { type: "message", role: "user", content: [{ type: "input_text", text }] },
    });
    this.send({ type: "response.create" });
  }

  /** Mid-session context change, e.g. the user scrubbed the video while chatting. */
  updateInstructions(instructions: string) {
    this.send({ type: "session.update", session: { instructions } });
  }

  cancel() {
    this.send({ type: "response.cancel" });
  }

  close() {
    this.ws?.close();
    this.ws = undefined;
  }

  private async handle(ev: ServerEvent) {
    switch (ev.type) {
      case "input_audio_buffer.speech_started":
        this.h.onSpeechStarted?.();
        break;
      case "conversation.item.input_audio_transcription.completed":
        this.h.onUserTranscript?.(ev.item_id, ev.transcript);
        break;
      case "response.output_audio.delta":
        this.h.onAudioDelta?.(ev.delta);
        break;
      case "response.output_audio_transcript.delta":
      case "response.output_text.delta": {
        const id = ev.item_id ?? ev.response_id;
        this.textBuf.set(id, (this.textBuf.get(id) ?? "") + ev.delta);
        this.h.onAssistantDelta?.(id, ev.delta);
        break;
      }
      case "response.output_audio_transcript.done":
        this.h.onAssistantDone?.(ev.item_id, ev.transcript);
        this.textBuf.delete(ev.item_id);
        break;
      case "response.output_text.done": {
        // no item_id on this event; flush whatever we buffered
        for (const [id, text] of this.textBuf) this.h.onAssistantDone?.(id, ev.text ?? text);
        this.textBuf.clear();
        break;
      }
      case "response.function_call_arguments.done": {
        let output = "Tool unavailable.";
        try {
          output = (await this.h.onToolCall?.(ev.name, JSON.parse(ev.arguments || "{}"))) ?? output;
        } catch (e) {
          this.h.onError?.(e);
        }
        this.send({
          type: "conversation.item.create",
          item: { type: "function_call_output", call_id: ev.call_id, output },
        });
        this.send({ type: "response.create" });
        break;
      }
      case "response.done":
        this.h.onResponseDone?.(ev.response?.status);
        break;
      case "error":
        this.h.onError?.(ev.error);
        break;
    }
  }
}
