/**
 * Browser client for Higgs Realtime (wss://api.boson.ai/v1/realtime).
 * Auth: ephemeral key from our backend, passed as the `bai-client-secret.<key>` subprotocol.
 * Event names: https://docs.boson.ai/api-reference/realtime/server-events
 */

export interface RealtimeHandlers {
  onUserTranscript?: (itemId: string, text: string) => void;
  onAssistantDelta?: (itemId: string, delta: string) => void; // transcript (audio mode) or text (text mode)
  onAssistantDone?: (itemId: string, text: string) => void;
  onAudioDelta?: (b64: string, itemId: string) => void;
  onSpeechStarted?: () => void; // user started talking -> barge-in
  onResponseDone?: (status: string) => void;
  onToolCall?: (name: string, args: unknown) => Promise<string>;
  onError?: (err: unknown) => void;
  onClose?: () => void;
}

type ServerEvent = { type: string; [k: string]: any };

/** Non-Latin scripts the model tends to answer in English otherwise. */
export function detectLanguage(text: string): string | null {
  if (/[぀-ヿ]/.test(text)) return "Japanese";
  if (/[가-힯]/.test(text)) return "Korean";
  if (/[一-鿿]/.test(text)) return "Chinese";
  if (/[Ѐ-ӿ]/.test(text)) return "Russian";
  return null;
}

export class RealtimeSession {
  private ws?: WebSocket;
  private textBuf = new Map<string, string>();
  // Response lifecycle, so a cancel is only sent while a response really runs. (Cancelling one that
  // has already finished makes the server answer "No active response to cancel".)
  private requested = 0; // response.create sent, response.created not seen yet
  private active = false; // between response.created and response.done
  private cancelOnStart = false; // cancel() came before the response had started
  /** Short instruction appended after every user turn (backend-provided). */
  turnNote = "";

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

  clearAudio() {
    this.send({ type: "input_audio_buffer.clear" });
  }

  /** Push-to-talk: end of the user's turn -> ask for a reply. */
  /** Push-to-talk: end of the user's spoken turn (the reply is requested with respond()). */
  commitAudio() {
    this.send({ type: "input_audio_buffer.commit" });
  }

  /** Ask for the reply: optional context notes (e.g. relevant memories), the director's note, go. */
  respond(notes: string[] = []) {
    for (const n of [...notes, this.turnNote].filter(Boolean)) {
      this.send({
        type: "conversation.item.create",
        item: { type: "message", role: "user", content: [{ type: "input_text", text: n }] },
      });
    }
    this.createResponse();
  }

  private createResponse(response?: Record<string, unknown>) {
    this.requested++;
    this.send(response ? { type: "response.create", response } : { type: "response.create" });
  }

  sendText(text: string, notes: string[] = []) {
    // The character's memories are in English, which pulls replies toward English.
    // A short hint keeps typed questions answered in the user's language.
    const lang = detectLanguage(text);
    const withHint = lang ? `${text}\n\n(Reply in ${lang}.)` : text;
    this.send({
      type: "conversation.item.create",
      item: { type: "message", role: "user", content: [{ type: "input_text", text: withHint }] },
    });
    this.respond(notes);
  }

  /** Mid-session context change, e.g. the user scrubbed the video while chatting. */
  updateInstructions(instructions: string) {
    this.send({ type: "session.update", session: { instructions } });
  }

  /** Stop the reply in progress (or the one just requested, as soon as it starts). */
  cancel() {
    if (this.active) this.send({ type: "response.cancel" });
    else if (this.requested > 0) this.cancelOnStart = true;
  }

  /** Remove an item from the conversation (e.g. a "question" that was only noise or echo). */
  deleteItem(itemId: string) {
    this.send({ type: "conversation.item.delete", item_id: itemId });
  }

  /** Make the character say exactly `text` (e.g. the spoiler-safe version of a line they started). */
  say(text: string) {
    this.cancelOnStart = false; // a fresh reply: an earlier cancel must not hit it
    this.createResponse({
      instructions: `Say exactly this, in character, in the same language, and nothing else: "${text.replace(/"/g, "'")}"`,
    });
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
        this.h.onAudioDelta?.(ev.delta, ev.item_id);
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
        this.createResponse();
        break;
      }
      case "response.created":
        this.requested = Math.max(0, this.requested - 1);
        this.active = true;
        if (this.cancelOnStart) {
          this.cancelOnStart = false;
          this.send({ type: "response.cancel" });
        }
        break;
      case "response.done":
        this.active = false;
        this.h.onResponseDone?.(ev.response?.status);
        break;
      case "error":
        // a cancel racing the end of a reply is harmless; don't show it to the user
        if (/no active response/i.test(String(ev.error?.message ?? ""))) break;
        this.h.onError?.(ev.error);
        break;
    }
  }
}
