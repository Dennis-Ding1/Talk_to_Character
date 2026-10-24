"""Summarise results/raw.jsonl from bench.py: summary.csv, report.md and the figures in plots/.

  .venv/Scripts/python.exe model_speed_test/analyze.py [--raw results/raw.jsonl]
"""

import argparse
import csv
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent

# Validated categorical slots (light surface); identity is also carried by legends and labels.
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3de"
TEXT_C, AUDIO_C, GEN_C = "#2a78d6", "#eb6834", "#1baf7a"
LENGTHS = ["short", "medium", "long"]
LEN_LABEL = {"short": "Short reply", "medium": "Medium reply", "long": "Long reply"}
COND_LABEL = {"avatar_text": "Text-driven (input_tts)", "avatar_audio": "Audio-driven (input = wav)"}
COND_COLOR = {"avatar_text": TEXT_C, "avatar_audio": AUDIO_C}

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "text.color": INK, "font.size": 11, "axes.titlesize": 14, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False,
})


def load(raw: Path) -> list[dict]:
    rows = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if "error" not in r]
    # Realtime is asked to read the text verbatim but sometimes stops early or shortens it. Only
    # complete reads (>= 90% of the TTS 3 audio length for the same text) count for its timing,
    # otherwise a cut-short reply would look faster than it is.
    tts_len = {L: mean([r["audio_s"] for r in rows if r["condition"] == "tts_full" and r["length"] == L])
               for L in {r["length"] for r in rows}}
    for r in rows:
        if r["condition"] == "realtime":
            r["complete"] = r["audio_s"] >= 0.9 * tts_len.get(r["length"], 0)
    return rows


def realtime_rows(rows):
    return [r for r in rows if r["condition"] != "realtime" or r.get("complete")]


def group(rows, cond, length, key):
    return [r[key] for r in rows if r["condition"] == cond and r["length"] == length and key in r]


def mean(xs):
    return st.mean(xs) if xs else float("nan")


def sd(xs):
    return st.stdev(xs) if len(xs) > 1 else 0.0


def med(xs):
    return st.median(xs) if xs else float("nan")


def caption(fig, text):
    fig.text(0.01, 0.01, text, fontsize=9, color=INK_2, ha="left", va="bottom")


def dot_bar_chart(rows, key, title, ylabel, path, note):
    """Mean bar + every trial as a dot, text vs audio side by side for each reply length."""
    fig, ax = plt.subplots(figsize=(9, 5.2))
    width = 0.36
    for j, cond in enumerate(["avatar_text", "avatar_audio"]):
        for i, length in enumerate(LENGTHS):
            xs = group(rows, cond, length, key)
            if not xs:
                continue
            x = i + (j - 0.5) * (width + 0.04)
            ax.bar(x, mean(xs), width, color=COND_COLOR[cond], alpha=0.9, edgecolor=SURFACE, linewidth=2,
                   label=COND_LABEL[cond] if i == 0 else None)
            ax.scatter([x + (k - (len(xs) - 1) / 2) * 0.03 for k in range(len(xs))], xs, s=22, color=INK,
                       zorder=3, linewidths=0)
            ax.annotate(f"{mean(xs):.1f} s", (x, max(max(xs), mean(xs))), xytext=(0, 8), textcoords="offset points",
                        ha="center", fontsize=10, color=INK, fontweight="bold")
    ax.set_xticks(range(len(LENGTHS)), [LEN_LABEL[n] for n in LENGTHS])
    ax.set_ylabel(ylabel)
    ax.set_title(title, pad=34)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=10)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.12)
    caption(fig, note)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=180)
    plt.close(fig)


def speed_chart(rows, path, n):
    fig, ax = plt.subplots(figsize=(9, 5.2))
    width = 0.36
    for j, cond in enumerate(["avatar_text", "avatar_audio"]):
        for i, length in enumerate(LENGTHS):
            xs = group(rows, cond, length, "render_speed_x")
            if not xs:
                continue
            x = i + (j - 0.5) * (width + 0.04)
            ax.scatter([x] * len(xs), xs, s=40, color=COND_COLOR[cond], zorder=3, linewidths=0,
                       label=COND_LABEL[cond] if i == 0 else None)
            ax.hlines(mean(xs), x - 0.13, x + 0.13, color=INK, linewidth=2, zorder=4)
            ax.annotate(f"{mean(xs):.2f}×", (x + 0.15, mean(xs)), va="center", fontsize=10, color=INK)
    ax.axhline(1.0, color=INK_2, linewidth=1.2, linestyle="--")
    ax.annotate("real time (playback speed)", (len(LENGTHS) - 0.5, 1.0), xytext=(0, 5), textcoords="offset points",
                ha="right", fontsize=9, color=INK_2)
    ax.set_xticks(range(len(LENGTHS)), [LEN_LABEL[n] for n in LENGTHS])
    ax.set_ylabel("Video seconds rendered per wall-clock second")
    ax.set_title("Render speed once frames start arriving", pad=34)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=10)
    ax.grid(axis="x", visible=False)
    ax.set_ylim(0, max(2.0, ax.get_ylim()[1]))
    caption(fig, f"Above the dashed line the stream outruns playback, so a short start buffer never stalls. "
                 f"Dots = trials (n={n} per bar), bar = mean.")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=180)
    plt.close(fig)


def curves_chart(rows, length, path):
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for cond in ["avatar_text", "avatar_audio"]:
        for k, r in enumerate(r for r in rows if r["condition"] == cond and r["length"] == length):
            ts, vs = zip(*r["curve"])
            ax.plot(ts, vs, color=COND_COLOR[cond], linewidth=2, alpha=0.75,
                    label=COND_LABEL[cond] if k == 0 else None)
    ax.set_xlabel("Seconds since the request was sent")
    ax.set_ylabel("Seconds of video received")
    ax.set_title(f"How the video arrives ({LEN_LABEL[length].lower()}, every trial)", pad=34)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=10)
    caption(fig, "Each line is one render. Further left = frames sooner; steeper = faster than real time.")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=180)
    plt.close(fig)


def pipelines(rows, length):
    """Mean seconds from 'reply text is ready' to 'avatar can play smoothly', per pipeline."""
    a_text = mean(group(rows, "avatar_text", length, "smooth_start_s"))
    a_audio = mean(group(rows, "avatar_audio", length, "smooth_start_s"))
    tts = mean(group(rows, "tts_full", length, "gen_s"))
    rt = mean(group(realtime_rows(rows), "realtime", length, "gen_s"))
    return [
        ("Text → Avatar\n(Avatar runs TTS itself)", 0.0, a_text, TEXT_C),
        ("Higgs TTS 3 → Avatar\n(whole wav, then render)", tts, a_audio, AUDIO_C),
        ("Higgs Realtime voice → Avatar\n(Realtime speaks, then render)", rt, a_audio, AUDIO_C),
    ]


def end_to_end_chart(rows, path):
    fig, axes = plt.subplots(1, len(LENGTHS), figsize=(13, 5.2), sharex=True)
    for ax, length in zip(axes, LENGTHS):
        items = pipelines(rows, length)
        for y, (name, gen, avatar, color) in enumerate(items):
            if gen > 0:
                ax.barh(y, gen, color=GEN_C, edgecolor=SURFACE, linewidth=2, height=0.55,
                        label="Generating the audio" if y == 1 else None)
            ax.barh(y, avatar, left=gen, color=color, edgecolor=SURFACE, linewidth=2, height=0.55)
            ax.annotate(f"{gen + avatar:.1f} s", (gen + avatar, y), xytext=(4, 0), textcoords="offset points",
                        va="center", fontsize=10, fontweight="bold", color=INK)
        ax.set_yticks(range(len(items)), [n for n, *_ in items] if ax is axes[0] else [""] * len(items))
        ax.invert_yaxis()
        ax.set_title(LEN_LABEL[length], fontsize=12)
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("Seconds until smooth playback")
    xmax = max(g + a for length in LENGTHS for _, g, a, _ in pipelines(rows, length))
    axes[0].set_xlim(0, xmax * 1.25)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (GEN_C, TEXT_C, AUDIO_C)]
    fig.legend(handles, ["Generating the audio", "Avatar, text-driven", "Avatar, audio-driven"],
               loc="upper right", ncol=3, fontsize=10)
    fig.suptitle("From finished reply text to a smoothly playing talking head", x=0.01, ha="left",
                 fontsize=14, fontweight="bold")
    caption(fig, "Means over all trials. 'Smooth playback' = earliest start after which no frame arrives late.")
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(HERE / "results" / "raw.jsonl"))
    args = ap.parse_args()
    raw = Path(args.raw)
    rows = load(raw)
    out_dir = raw.parent
    plots = HERE / "plots"
    plots.mkdir(exist_ok=True)

    # summary table
    metrics = {"avatar_text": ["first_bytes_s", "first_frame_s", "smooth_start_s", "render_speed_x", "video_s"],
               "avatar_audio": ["first_bytes_s", "first_frame_s", "smooth_start_s", "render_speed_x", "video_s"],
               "tts_full": ["gen_s", "audio_s"], "realtime": ["first_audio_s", "gen_s", "audio_s"]}
    table = []
    for cond, keys in metrics.items():
        for length in LENGTHS:
            for key in keys:
                xs = group(rows, cond, length, key)
                if xs:
                    table.append({"condition": cond, "length": length, "metric": key, "n": len(xs),
                                  "mean": round(mean(xs), 3), "sd": round(sd(xs), 3), "median": round(med(xs), 3),
                                  "min": round(min(xs), 3), "max": round(max(xs), 3)})
    with (out_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)

    n = max((len(group(rows, "avatar_text", L, "smooth_start_s")) for L in LENGTHS), default=0)
    dot_bar_chart(rows, "smooth_start_s", "Time until the talking head can play without stalling",
                  "Seconds after the request", plots / "1_smooth_start.png",
                  f"Earliest start time after which no frame arrives late. Dots = trials (n={n} per bar), bar = mean.")
    dot_bar_chart(rows, "first_frame_s", "Time to the first video frame", "Seconds after the request",
                  plots / "2_first_frame.png", f"Dots = trials (n={n} per bar), bar = mean.")
    speed_chart(rows, plots / "3_render_speed.png", n)
    curves_chart(rows, "long", plots / "4_arrival_long.png")
    end_to_end_chart(rows, plots / "5_end_to_end.png")

    # report
    def cell(cond, length, key, unit="s"):
        xs = group(rows, cond, length, key)
        return f"{mean(xs):.2f} ± {sd(xs):.2f}{unit}" if xs else "–"

    lines = ["# Results", "", f"Trials per cell: {n}. Values are mean ± standard deviation.", "",
             "| Reply | Audio length | Smooth start, text-driven | Smooth start, audio-driven | Saved |"
             " First frame, text | First frame, audio | Render speed, text | Render speed, audio |",
             "|---|---|---|---|---|---|---|---|---|"]
    for length in LENGTHS:
        t = mean(group(rows, "avatar_text", length, "smooth_start_s"))
        a = mean(group(rows, "avatar_audio", length, "smooth_start_s"))
        lines.append(
            f"| {LEN_LABEL[length]} | {mean(group(rows, 'avatar_audio', length, 'video_s')):.1f} s"
            f" | {cell('avatar_text', length, 'smooth_start_s')} | {cell('avatar_audio', length, 'smooth_start_s')}"
            f" | **{t - a:.1f} s ({(t - a) / t:.0%})**"
            f" | {cell('avatar_text', length, 'first_frame_s')} | {cell('avatar_audio', length, 'first_frame_s')}"
            f" | {cell('avatar_text', length, 'render_speed_x', '×')} | {cell('avatar_audio', length, 'render_speed_x', '×')} |")
    lines += ["", "Audio generation (whole reply):", "",
              "| Reply | Higgs TTS 3 (wav) | Higgs Realtime (first audio) | Higgs Realtime (whole reply) |",
              "|---|---|---|---|"]
    complete = realtime_rows(rows)
    for length in LENGTHS:
        all_rt = [r for r in rows if r["condition"] == "realtime" and r["length"] == length]
        ok = [r for r in all_rt if r.get("complete")]
        xs = [r["gen_s"] for r in ok]
        lines.append(f"| {LEN_LABEL[length]} | {cell('tts_full', length, 'gen_s')} | {cell('realtime', length, 'first_audio_s')}"
                     f" | {mean(xs):.2f} ± {sd(xs):.2f}s (complete reads: {len(ok)}/{len(all_rt)}) |")
    lines += ["", "Realtime was asked to read the text verbatim; reads that stopped early (audio < 90% of the "
              "TTS 3 length) are excluded from its whole-reply time."]
    lines += ["", "End to end, from finished reply text to smooth playback (means):", "",
              "| Reply | Text → Avatar | TTS 3 → Avatar | Realtime → Avatar |", "|---|---|---|---|"]
    for length in LENGTHS:
        p = pipelines(rows, length)
        lines.append(f"| {LEN_LABEL[length]} | " + " | ".join(f"{g + a:.1f} s" for _, g, a, _ in p) + " |")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {out_dir / 'summary.csv'}, {out_dir / 'report.md'}, plots in {plots}")


if __name__ == "__main__":
    main()
