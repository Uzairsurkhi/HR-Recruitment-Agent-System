from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hr_agent.agents.chatbot_agent import ChatbotAgentGraph
from hr_agent.db.session import async_session_factory

router = APIRouter()


@router.websocket("/ws/hr-chat")
async def hr_chat_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    graph = ChatbotAgentGraph()
    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            text = (msg.get("message") or "").strip()
            if not text:
                await websocket.send_text(json.dumps({"type": "error", "message": "empty message"}))
                continue
            async with async_session_factory() as session:
                out = await graph.run(
                    session,
                    {"user_message": text},
                )
                await session.commit()
            await websocket.send_text(json.dumps({"type": "message", "text": out.get("reply", "")}))
    except WebSocketDisconnect:
        return
