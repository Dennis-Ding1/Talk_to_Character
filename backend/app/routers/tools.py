"""Executes Realtime function calls. The browser receives the call from Higgs and forwards it here;
we answer from t-filtered knowledge only, so tools can't leak spoilers either."""

from fastapi import APIRouter, HTTPException

from app.context.knowledge import MovieNotFound, load_movie
from app.context.persona import fmt_scene
from app.context.retrieval import search_scenes
from app.schemas import ToolCall

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.post("/{name}")
def run_tool(name: str, call: ToolCall) -> dict:
    try:
        kb = load_movie(call.movie_id)
        kb.character(call.character_id)
    except (MovieNotFound, KeyError):
        raise HTTPException(404, "movie or character not found")

    if name == "recall_scene":
        known = (kb.all_scenes_of(call.character_id) if call.knowledge == "omniscient"
                 else kb.known_scenes(call.character_id, call.t))
        hits = search_scenes(known, call.arguments.get("query", ""))
        if not hits:
            return {"result": "You don't remember anything like that."}
        return {"result": "\n\n".join(fmt_scene(s, {cid: ch.name for cid, ch in kb.characters.items()}) for s in hits)}

    if name == "get_relationship":
        other = (call.arguments.get("other") or "").strip().lower()
        match = next(
            (
                c
                for c in kb.characters.values()
                if other in {c.id.lower(), c.name.lower(), *(a.lower() for a in c.aliases)}
            ),
            None,
        )
        if match is None:
            return {"result": f"You don't know anyone called {other!r}."}
        me = kb.character(call.character_id)
        st = (kb.final_state(call.character_id) if call.knowledge == "omniscient"
              else kb.state_at(call.character_id, call.t))
        rel = (st.relationships.get(match.id) if st else None) or me.relationships.get(match.id)
        return {"result": rel or f"You have no strong feelings about {match.name} yet."}

    raise HTTPException(404, f"unknown tool {name!r}")
