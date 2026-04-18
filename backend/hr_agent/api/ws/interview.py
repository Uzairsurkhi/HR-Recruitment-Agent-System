import json
import time
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hr_agent.agents.technical_interview_agent import TechnicalInterviewGraph, TIState
from hr_agent.config import get_settings
from hr_agent.db.session import async_session_factory

router = APIRouter()

SESSION_CACHE: dict[str, dict[str, Any]] = {}


def _question_index_from_state(d: dict[str, Any]) -> int:
    """Aligns with TIState: count of answers completed so far (before current answer)."""
    if "question_index" in d and d.get("question_index") is not None:
        return int(d["question_index"])
    return len(d.get("transcript") or [])


@router.websocket("/ws/interview")
async def interview_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    settings = get_settings()
    slack = 5.0
    deadline_monotonic: Optional[float] = None
    graph = TechnicalInterviewGraph()

    async def send_json(data: dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(data))

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")
            async with async_session_factory() as session:
                if mtype == "start":
                    session_id = msg.get("session_id")
                    candidate_id = msg.get("candidate_id")
                    level = msg.get("experience_level", "mid")
                    if not session_id or not candidate_id:
                        await send_json({"type": "error", "message": "session_id and candidate_id required"})
                        continue
                    state: TIState = {
                        "session_id": session_id,
                        "candidate_id": candidate_id,
                        "experience_level": level,
                        "question_index": 0,
                        "transcript": [],
                        "last_answer": None,
                        "done": False,
                    }
                    out = await graph.run_turn(session, state)
                    await session.commit()
                    SESSION_CACHE[session_id] = dict(out)
                    deadline_monotonic = time.monotonic() + settings.interview_answer_seconds + slack
                    await send_json(
                        {
                            "type": "question",
                            "text": out.get("current_question", ""),
                            "question_index": _question_index_from_state(out),
                            "answer_seconds": settings.interview_answer_seconds,
                            "server_deadline_monotonic": deadline_monotonic,
                        }
                    )
                elif mtype == "answer":
                    text = (msg.get("text") or "").strip()
                    session_id = msg.get("session_id")
                    candidate_id = msg.get("candidate_id")
                    level = msg.get("experience_level", "mid")
                    if not session_id or session_id not in SESSION_CACHE:
                        await send_json({"type": "error", "message": "start session first"})
                        continue
                    if deadline_monotonic is not None and time.monotonic() > deadline_monotonic:
                        await send_json({"type": "error", "message": "answer_timeout"})
                        deadline_monotonic = None
                        continue
                    base = SESSION_CACHE[session_id]
                    st: TIState = {
                        "session_id": session_id,
                        "candidate_id": candidate_id,
                        "experience_level": level,
                        "question_index": _question_index_from_state(base),
                        "transcript": list(base.get("transcript") or []),
                        "current_question": base.get("current_question", ""),
                        "last_answer": text,
                        "done": bool(base.get("done")),
                    }
                    out = await graph.run_turn(session, st)
                    await session.commit()
                    SESSION_CACHE[session_id] = dict(out)
                    if out.get("done"):
                        SESSION_CACHE.pop(session_id, None)
                        await send_json(
                            {
                                "type": "complete",
                                "transcript": out.get("transcript", []),
                            }
                        )
                        deadline_monotonic = None
                        continue
                    deadline_monotonic = time.monotonic() + settings.interview_answer_seconds + slack
                    await send_json(
                        {
                            "type": "question",
                            "text": out.get("current_question", ""),
                            "question_index": _question_index_from_state(out),
                            "answer_seconds": settings.interview_answer_seconds,
                            "server_deadline_monotonic": deadline_monotonic,
                        }
                    )
                else:
                    await send_json({"type": "error", "message": "unknown type"})
    except WebSocketDisconnect:
        return
