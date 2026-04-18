import json
from typing import Any, Optional

import httpx

from hr_agent.config import Settings, get_settings


class LLMService:
    """Async OpenAI-compatible chat + JSON helpers. Supports mock mode for demos."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        if self.settings.mock_llm or not self.settings.openai_api_key:
            return self._mock_json(system, user)
        payload = {
            "model": self.settings.openai_model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)

    async def chat_text(self, system: str, user: str, *, temperature: float = 0.3) -> str:
        if self.settings.mock_llm or not self.settings.openai_api_key:
            return "[mock] " + user[:200]
        payload = {
            "model": self.settings.openai_model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=self._headers(),
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]

    def _mock_json(self, system: str, user: str) -> dict[str, Any]:
        if "ATS" in system or "score" in system.lower():
            return {
                "skill_match": 0.82,
                "experience_alignment": 0.78,
                "keyword_relevance": 0.85,
                "overall_score": 81.5,
                "rationale": "Mock: strong keyword overlap with JD; experience aligns with mid-level role.",
            }
        if "technical" in system.lower() and "question" in system.lower():
            return {
                "question": "Mock: Explain how you would design a REST API rate limiter.",
            }
        if "evaluate" in system.lower() or "score" in user.lower():
            return {
                "score": 7.5,
                "reasoning": "Mock evaluation: answer shows structured thinking.",
            }
        if "screening" in system.lower() or "notice" in system.lower():
            return {
                "questions": [
                    {
                        "id": "q1",
                        "text": "What is your notice period and earliest joining date?",
                        "topic": "availability",
                    },
                    {
                        "id": "q2",
                        "text": "Confirm your highest degree and graduation year.",
                        "topic": "education",
                    },
                ]
            }
        if "chatbot" in system.lower() or "SQL" in system:
            return {"reply": "Mock: please set OPENAI_API_KEY for grounded DB answers.", "sql": None}
        return {"result": "ok", "raw": user[:200]}
