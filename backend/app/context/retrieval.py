"""BM25 search over the scenes a character knows (already cut at t). Works for CJK + Latin text."""

import re

from rank_bm25 import BM25Okapi

from app.schemas import Scene

_TOKEN_RE = re.compile(r"[一-鿿぀-ヿ가-힯]|[a-zA-Z0-9']+")


def tokenize(text: str) -> list[str]:
    # CJK: one token per character; Latin: words.
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


def scene_text(s: Scene) -> str:
    return " ".join([s.summary, *s.key_events, *(ln.text for ln in s.lines), *(b.text for b in s.beats)])


def search_scenes(scenes: list[Scene], query: str, k: int = 3) -> list[Scene]:
    if not scenes:
        return []
    corpus = [tokenize(scene_text(s)) or ["_"] for s in scenes]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip(scores, range(len(scenes))), key=lambda x: -x[0])
    return [scenes[i] for score, i in ranked[:k] if score > 0]
