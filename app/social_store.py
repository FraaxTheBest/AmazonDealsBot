from __future__ import annotations

from datetime import datetime, timezone
import json

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, SessionLocal
from app.social.base import SocialPost


STATUS_OPEN = "open"
STATUS_PUBLISHED = "published"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"

PLATFORMS = ("facebook", "instagram", "pinterest", "telegram", "whatsapp")


class SocialDraft(Base):
    __tablename__ = "social_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)

    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    link: Mapped[str] = mapped_column(Text, default="", nullable=False)
    image_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hashtags: Mapped[str] = mapped_column(Text, default="", nullable=False)

    destinations_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    publish_results_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=STATUS_OPEN, index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def destinations(self) -> list[str]:
        try:
            values = json.loads(self.destinations_json or "[]")
        except json.JSONDecodeError:
            return []
        if not isinstance(values, list):
            return []
        return [str(value) for value in values if str(value) in PLATFORMS]

    def post(self) -> SocialPost:
        return SocialPost(
            title=self.title or "",
            description=self.description or "",
            link=self.link or "",
            image_url=self.image_url or "",
            hashtags=self.hashtags or "",
        )


async def create_social_draft(
    owner_telegram_user_id: int,
    post: SocialPost,
    destinations: list[str],
) -> SocialDraft:
    clean_destinations = [p for p in PLATFORMS if p in set(destinations)]
    async with SessionLocal() as session:
        draft = SocialDraft(
            owner_telegram_user_id=owner_telegram_user_id,
            title=post.title.strip(),
            description=post.description.strip(),
            link=post.link.strip(),
            image_url=post.image_url.strip(),
            hashtags=post.hashtags.strip(),
            destinations_json=json.dumps(clean_destinations),
            status=STATUS_OPEN,
        )
        session.add(draft)
        await session.commit()
        await session.refresh(draft)
        return draft


async def get_social_draft(owner_telegram_user_id: int, draft_id: int) -> SocialDraft | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(SocialDraft).where(
                SocialDraft.id == draft_id,
                SocialDraft.owner_telegram_user_id == owner_telegram_user_id,
            )
        )
        return result.scalar_one_or_none()


async def list_social_drafts(owner_telegram_user_id: int, limit: int = 20) -> list[SocialDraft]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(SocialDraft)
            .where(SocialDraft.owner_telegram_user_id == owner_telegram_user_id)
            .order_by(SocialDraft.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def update_social_field(
    owner_telegram_user_id: int,
    draft_id: int,
    field: str,
    value: str,
) -> SocialDraft | None:
    allowed = {"title", "description", "link", "image_url", "hashtags"}
    if field not in allowed:
        raise ValueError("Campo social non modificabile.")

    async with SessionLocal() as session:
        result = await session.execute(
            select(SocialDraft).where(
                SocialDraft.id == draft_id,
                SocialDraft.owner_telegram_user_id == owner_telegram_user_id,
            )
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            return None
        setattr(draft, field, value.strip())
        draft.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(draft)
        return draft


async def toggle_social_destination(
    owner_telegram_user_id: int,
    draft_id: int,
    platform: str,
) -> SocialDraft | None:
    if platform not in PLATFORMS:
        raise ValueError("Piattaforma non valida.")

    async with SessionLocal() as session:
        result = await session.execute(
            select(SocialDraft).where(
                SocialDraft.id == draft_id,
                SocialDraft.owner_telegram_user_id == owner_telegram_user_id,
            )
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            return None

        destinations = draft.destinations()
        if platform in destinations:
            destinations.remove(platform)
        else:
            destinations.append(platform)
        destinations = [p for p in PLATFORMS if p in set(destinations)]
        draft.destinations_json = json.dumps(destinations)
        draft.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(draft)
        return draft


async def save_publish_results(
    owner_telegram_user_id: int,
    draft_id: int,
    results: dict,
    status: str,
) -> SocialDraft | None:
    if status not in {STATUS_OPEN, STATUS_PUBLISHED, STATUS_PARTIAL, STATUS_FAILED}:
        raise ValueError("Stato social non valido.")

    async with SessionLocal() as session:
        result = await session.execute(
            select(SocialDraft).where(
                SocialDraft.id == draft_id,
                SocialDraft.owner_telegram_user_id == owner_telegram_user_id,
            )
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            return None
        draft.publish_results_json = json.dumps(results, ensure_ascii=False)
        draft.status = status
        draft.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(draft)
        return draft
