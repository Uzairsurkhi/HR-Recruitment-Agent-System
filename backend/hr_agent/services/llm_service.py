import hashlib
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

    def _mock_ats_scores(self, user: str) -> dict[str, Any]:
        """Deterministic but varied demo scores from resume/JD text (no fixed 81.5)."""
        digest = hashlib.sha256(user.encode("utf-8", errors="replace")).digest()

        def frac(i: int) -> float:
            b = digest[i % len(digest)]
            return 0.28 + (b / 255.0) * 0.70  # ~0.28–0.98

        sm = round(frac(0), 2)
        ea = round(frac(3), 2)
        kr = round(frac(6), 2)
        overall = round((sm * 0.4 + ea * 0.35 + kr * 0.25) * 100, 1)
        overall = max(0.0, min(100.0, overall))
        return {
            "skill_match": sm,
            "experience_alignment": ea,
            "keyword_relevance": kr,
            "overall_score": overall,
            "rationale": (
                "Mock ATS (deterministic from resume/JD hash). "
                "Set OPENAI_API_KEY and MOCK_LLM=false for real LLM scoring."
            ),
        }

    def _mock_json(self, system: str, user: str) -> dict[str, Any]:
        if "ATS scoring engine" in system:
            return self._mock_ats_scores(user)
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
