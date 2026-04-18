from typing import Any, Optional

import httpx
import numpy as np

from hr_agent.config import Settings, get_settings


def _chunk_text(text: str, max_chars: int = 800) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + max_chars])
        start += max_chars
    return chunks


def _cosine(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


class RAGService:
    """Lightweight embedding RAG: chunk resume + JD, retrieve top chunks for LLM context."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        if self.settings.mock_llm or not self.settings.openai_api_key:
            # Deterministic fake vectors for ordering stability in mock mode
            out: list[list[float]] = []
            for i, t in enumerate(texts):
                vec = [float((ord(c) + i) % 17) / 17.0 for c in t[:64].ljust(64)]
                out.append(vec)
            return out
        payload = {"model": self.settings.openai_embedding_model, "input": texts}
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers=self._headers(),
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
        return [d["embedding"] for d in sorted(data["data"], key=lambda x: x["index"])]

    async def build_ats_context(self, resume: str, job_description: str) -> dict[str, Any]:
        resume_chunks = _chunk_text(resume, 900)
        jd_chunks = _chunk_text(job_description, 900)
        if not resume_chunks:
            resume_chunks = ["(empty resume)"]
        if not jd_chunks:
            jd_chunks = ["(empty jd)"]

        r_emb = await self._embed(resume_chunks)
        j_emb = await self._embed(jd_chunks)
        jd_centroid = np.mean(np.array(j_emb), axis=0).tolist()
        scored: list[tuple[float, str]] = []
        # strict= requires Python 3.10+; keep 3.9 compatible
        for emb, ch in zip(r_emb, resume_chunks):
            scored.append((_cosine(emb, jd_centroid), ch))
        scored.sort(key=lambda x: x[0], reverse=True)
        top_k = scored[: min(5, len(scored))]
        retrieval_score = float(np.mean([s for s, _ in top_k])) if top_k else 0.0
        context_block = "\n---\n".join(f"[chunk relevance={s:.3f}]\n{c}" for s, c in top_k)
        return {
            "top_chunks": [{"score": s, "text": c} for s, c in top_k],
            "retrieval_score": retrieval_score,
            "context_for_llm": context_block,
        }

    async def candidate_snippets_for_chatbot(self, resumes: list[tuple[str, str]]) -> str:
        """resumes: list of (candidate_id, resume_text) — returns condensed RAG context."""
        lines: list[str] = []
        for cid, text in resumes[:50]:
            ctx = await self.build_ats_context(text[:4000], "summary keywords role skills")
            snippet = ctx["context_for_llm"][:1200]
            lines.append(f"Candidate {cid}:\n{snippet}")
        return "\n\n".join(lines)
