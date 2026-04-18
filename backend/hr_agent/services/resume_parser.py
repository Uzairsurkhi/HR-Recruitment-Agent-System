from io import BytesIO


async def extract_text_from_upload(filename: str, raw: bytes) -> str:
    """Best-effort text extraction for PDF/DOCX/TXT."""
    lower = filename.lower()
    if lower.endswith(".txt"):
        return raw.decode("utf-8", errors="replace")

    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(raw))
            parts: list[str] = []
            for page in reader.pages:
                parts.append(page.extract_text() or "")
            return "\n".join(parts).strip() or raw.decode("utf-8", errors="replace")
        except Exception:
            return raw.decode("utf-8", errors="replace")

    if lower.endswith(".docx"):
        try:
            import docx

            doc = docx.Document(BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            return raw.decode("utf-8", errors="replace")

    return raw.decode("utf-8", errors="replace")
