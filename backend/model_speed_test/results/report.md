# Results

Trials per cell: 5. Values are mean ± standard deviation.

| Reply | Audio length | Smooth start, text-driven | Smooth start, audio-driven | Saved | First frame, text | First frame, audio | Render speed, text | Render speed, audio |
|---|---|---|---|---|---|---|---|---|
| Short reply | 3.8 s | 4.60 ± 0.18s | 2.32 ± 0.10s | **2.3 s (50%)** | 4.60 ± 0.18s | 2.32 ± 0.10s | 2.15 ± 0.25× | 2.16 ± 0.04× |
| Medium reply | 9.8 s | 5.60 ± 0.44s | 2.53 ± 0.18s | **3.1 s (55%)** | 4.54 ± 0.12s | 2.53 ± 0.18s | 1.11 ± 0.06× | 1.48 ± 0.01× |
| Long reply | 19.6 s | 7.91 ± 0.38s | 2.96 ± 0.47s | **5.0 s (63%)** | 4.68 ± 0.17s | 2.96 ± 0.47s | 0.94 ± 0.01× | 1.33 ± 0.02× |

Audio generation (whole reply):

| Reply | Higgs TTS 3 (wav) | Higgs Realtime (first audio) | Higgs Realtime (whole reply) |
|---|---|---|---|
| Short reply | 1.06 ± 0.08s | 0.41 ± 0.04s | 0.79 ± 0.06s (complete reads: 4/5) |
| Medium reply | 2.57 ± 0.13s | 0.41 ± 0.08s | 1.59 ± 0.05s (complete reads: 4/5) |
| Long reply | 5.40 ± 0.12s | 0.65 ± 0.57s | 2.68 ± 0.02s (complete reads: 2/5) |

Realtime was asked to read the text verbatim; reads that stopped early (audio < 90% of the TTS 3 length) are excluded from its whole-reply time.

End to end, from finished reply text to smooth playback (means):

| Reply | Text → Avatar | TTS 3 → Avatar | Realtime → Avatar |
|---|---|---|---|
| Short reply | 4.6 s | 3.4 s | 3.1 s |
| Medium reply | 5.6 s | 5.1 s | 4.1 s |
| Long reply | 7.9 s | 8.4 s | 5.6 s |
