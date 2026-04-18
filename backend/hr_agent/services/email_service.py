import hashlib
from datetime import datetime
from typing import Optional

import aiosmtplib
from email.message import EmailMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hr_agent.config import get_settings
from hr_agent.db.models import EmailLog


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def send_if_new(
        self,
        session: AsyncSession,
        *,
        template_key: str,
        candidate_id: Optional[str],
        recipient: str,
        subject: str,
        body: str,
    ) -> bool:
        existing = await session.execute(
            select(EmailLog).where(
                EmailLog.template_key == template_key,
                EmailLog.candidate_id == candidate_id,
            )
        )
        if existing.scalar_one_or_none():
            return False

        preview = body[:2000]
        log = EmailLog(
            template_key=template_key,
            candidate_id=candidate_id,
            recipient=recipient,
            subject=subject,
            body_preview=preview,
            created_at=datetime.utcnow(),
        )
        session.add(log)
        await session.flush()

        if self.settings.mock_email:
            return True

        msg = EmailMessage()
        msg["From"] = self.settings.smtp_user or "noreply@localhost"
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)

        await aiosmtplib.send(
            msg,
            hostname=self.settings.smtp_host,
            port=self.settings.smtp_port,
            username=self.settings.smtp_user or None,
            password=self.settings.smtp_password or None,
        )
        return True

    @staticmethod
    def body_hash(body: str) -> str:
        return hashlib.sha256(body.encode()).hexdigest()[:16]
