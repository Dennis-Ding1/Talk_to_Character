# Talk to Character: presentation script

About **5 minutes of talking**, plus a **3-minute live demo**, so about 8 minutes on stage.
About 580 words, so roughly 120 words a minute, which leaves room for the animations. **[click]** marks a click or →.

| # | Slide | Time | Ends at |
|---|---|---|---|
| 1 | Cover | 0:20 | 0:20 |
| 2 | The idea | 0:15 | 0:35 |
| 3 | The hard part | 0:25 | 1:00 |
| 4 | What keeps them in the moment | 0:50 | 1:50 |
| 5 | Pause. Click. Talk. | 0:30 | 2:20 |
| 6 | Small things that make it feel live | 0:20 | 2:40 |
| 7 | **Live demo** | 3:00 | 5:40 |
| 8 | Two performances | 0:20 | 6:00 |
| 9 | Three Higgs models | 0:20 | 6:20 |
| 10 | From video.mp4 to a reply | 0:30 | 6:50 |
| 11 | Latency budget | 0:15 | 7:05 |
| 12 | Emotion tags cost about two seconds | 0:25 | 7:30 |
| 13 | Limits | 0:25 | 7:55 |
| 14 | Close | 0:05 | 8:00 |

---

### 1 · Cover (0:20)
Hi, we're Haochen, Rolland and Yinuo. Imagine you're watching a film, and you hit pause.
**[click]** The character turns around, breaks through the screen, and talks to you. That's Talk to Character.

### 2 · The idea (0:15)
There's one rule. They talk to you as the person they are at the moment you paused. Pause at minute 47, and they remember everything up to minute 47. Nothing after.

### 3 · The hard part (0:25)
So why not just use a normal chatbot? Because it plays a character like an actor who has read the whole script.
**[click]** Ask it whether the test worked, and it just tells you.
**[click]** Ours checks every sentence before it's spoken, so he answers like a man who doesn't know yet.

### 4 · What keeps them in the moment (0:50)
Here's the rule we built around: only the guard ever sees the future, and the guard never talks to you. Three layers keep it that way. First, the playhead runs to the pause.
**[click]** Layer one cuts the knowledge. Nothing after the pause, no scene he wasn't in, and the scene you paused in keeps only its first half.
**[click]** Layer two is story time. The film jumps between decades. This is the order you watch it in.
**[click]** And this is the order he lived it in. He can't remember 1954, even though you've already seen it.
**[click]** Layer three is the guard. It checks every sentence before it's spoken. The second one gives away a result, so it's rewritten in his own voice.

### 5 · Pause. Click. Talk. (0:30)
Here's what it looks like in the app.
**[click]** You pause, and the room lights come up.
**[click]** We find the faces in that exact frame.
**[click]** Click one, and the character takes a seat.
**[click]** Then you just talk, by voice or by text, in any language, and the reply comes back in their cloned voice.

### 6 · Small things that make it feel live (0:20)
Two small things make it feel live.
**[click]** You can cut him off mid-sentence, and he stops and listens.
**[click]** And while the avatar renders, an idle clip keeps his face moving, so you never see a frozen frame. Let's show you.

### 7 · Live demo (3:00)
Switch to the app. Keep a backup screen recording open in another tab.
1. Pause before the Trinity test and click Oppenheimer's face.
2. Ask "Did the test work?" He doesn't know yet.
3. Ask again in Chinese. Same voice, and the answer comes back in Chinese.
4. Interrupt him mid-answer. He stops and listens.
5. Turn on Omniscience and ask again. Now he knows how it ends.
6. Switch to Rick and Morty and ask Rick something. Point out how fast and loud he talks next to Oppenheimer.

Come back to the deck at about 5:40.

### 8 · Two performances (0:20)
You heard how differently Oppenheimer and Rick talk.
**[click]** Oppenheimer is subtle. No tags get added, so his line goes to TTS as it is.
**[click]** Rick is expressive. "Fast speech" becomes a speed tag, "Wait, what?!" becomes surprise, and the burp in his line becomes a sound effect. A few settings per character.

### 9 · Three Higgs models (0:20)
Everything you just saw runs on Higgs. Realtime is the mind and the voice. TTS 3 gives us the cloned voice with emotion tags. Avatar turns one still into a talking face. And Realtime has a second job, as the spoiler guard.

### 10 · From video.mp4 to a reply (0:30)
Here's the whole pipeline.
**[click]** Once per film, we take faces from the video frames, scenes and speakers from the subtitles and screenplay, summaries written one scene at a time, and a cloned voice from the audio.
**[click]** Then on every pause, we find the faces, filter to time t, let Realtime write, have the guard check it, and speak.

### 11 · Latency budget (0:15)
We measured every call. Realtime's first audio arrives in about 0.4 seconds. The lip-synced face needs about three. So voice comes first, and the face is opt-in.

### 12 · Emotion tags cost about two seconds (0:25)
Emotion has a price, too. Realtime audio is the fastest path, but its emotion comes only from how the persona is written. TTS 3 takes explicit emotion and prosody tags, and that costs one and a half to two seconds more. So each film chooses.

### 13 · Limits (0:25)
What's still hard. Lip-sync takes seconds, and longer with emotion tags. Animated faces need hand setup, because face models are trained on real people. The guard is an LLM too, and we haven't measured how often it misses. And every new film takes setup.

### 14 · Close (0:05)
Talk to Character, through the fourth wall. Thank you.
