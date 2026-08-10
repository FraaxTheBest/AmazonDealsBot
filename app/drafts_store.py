import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from app.amazon.models import ProductSnapshot
from app.database import Base, Channel, SessionLocal, User


STATUS_OPEN = "open"
STATUS_PUBLISHING = "publishing"
STATUS_PUBLISHED = "published"
STATUS_DISCARDED = "discarded"
STATUS_FAILED = "failed"


class PostDraft(Base):
    __tablename__ = "post_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False, index=True)
    product_json: Mapped[str] = mapped_column(Text, nullable=False)
    post_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=STATUS_OPEN, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def draft_product(draft: PostDraft) -> ProductSnapshot:
    return ProductSnapshot.model_validate(json.loads(draft.product_json))


async def _owner_channel(session, owner_telegram_user_id: int, channel_id: int):
    result = await session.execute(
        select(User, Channel)
        .join(Channel, Channel.owner_id == User.id)
        .where(
            User.telegram_user_id == owner_telegram_user_id,
            Channel.id == channel_id,
            Channel.is_active.is_(True),
        )
    )
    return result.first()


async def create_draft(
    owner_telegram_user_id: int,
    channel_id: int,
    product: ProductSnapshot,
    post_text: str,
    source: str = "manual",
) -> PostDraft:
    async with SessionLocal() as session:
        row = await _owner_channel(session, owner_telegram_user_id, channel_id)
        if row is None:
            raise ValueError("Canale non disponibile.")
        owner, channel = row
        draft = PostDraft(
            owner_id=owner.id,
            channel_id=channel.id,
            product_json=json.dumps(product.model_dump(mode="json"), ensure_ascii=False),
            post_text=post_text,
            source=(source.strip().lower()[:30] or "manual"),
            status=STATUS_OPEN,
        )
        session.add(draft)
        await session.commit()
        await session.refresh(draft)
        return draft


async def list_open_drafts(
    owner_telegram_user_id: int,
    channel_id: int | None = None,
    limit: int = 100,
) -> list[tuple[PostDraft, Channel]]:
    async with SessionLocal() as session:
        statement = (
            select(PostDraft, Channel)
            .join(Channel, PostDraft.channel_id == Channel.id)
            .join(User, PostDraft.owner_id == User.id)
            .where(
                User.telegram_user_id == owner_telegram_user_id,
                PostDraft.status == STATUS_OPEN,
            )
        )
        if channel_id is not None:
            statement = statement.where(PostDraft.channel_id == channel_id)
        result = await session.execute(
            statement.order_by(PostDraft.created_at.desc()).limit(max(1, min(int(limit), 500)))
        )
        return [(row[0], row[1]) for row in result.all()]


async def get_owner_draft(
    owner_telegram_user_id: int,
    draft_id: int,
) -> tuple[PostDraft, Channel] | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(PostDraft, Channel)
            .join(Channel, PostDraft.channel_id == Channel.id)
            .join(User, PostDraft.owner_id == User.id)
            .where(
                PostDraft.id == draft_id,
                User.telegram_user_id == owner_telegram_user_id,
            )
        )
        row = result.first()
        return (row[0], row[1]) if row else None


async def discard_draft(owner_telegram_user_id: int, draft_id: int) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(PostDraft)
            .join(User, PostDraft.owner_id == User.id)
            .where(
                PostDraft.id == draft_id,
                User.telegram_user_id == owner_telegram_user_id,
                PostDraft.status == STATUS_OPEN,
            )
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            return False
        draft.status = STATUS_DISCARDED
        draft.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return True


async def claim_draft_for_publish(
    owner_telegram_user_id: int,
    draft_id: int,
) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(PostDraft)
            .join(User, PostDraft.owner_id == User.id)
            .where(
                PostDraft.id == draft_id,
                User.telegram_user_id == owner_telegram_user_id,
                PostDraft.status == STATUS_OPEN,
            )
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            return False
        draft.status = STATUS_PUBLISHING
        draft.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return True


async def restore_draft_open(
    owner_telegram_user_id: int,
    draft_id: int,
) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(PostDraft)
            .join(User, PostDraft.owner_id == User.id)
            .where(
                PostDraft.id == draft_id,
                User.telegram_user_id == owner_telegram_user_id,
                PostDraft.status == STATUS_PUBLISHING,
            )
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            return False
        draft.status = STATUS_OPEN
        draft.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return True


async def mark_draft_failed_terminal(
    owner_telegram_user_id: int,
    draft_id: int,
) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(PostDraft)
            .join(User, PostDraft.owner_id == User.id)
            .where(
                PostDraft.id == draft_id,
                User.telegram_user_id == owner_telegram_user_id,
            )
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            return False
        draft.status = STATUS_FAILED
        draft.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return True


async def mark_draft_published(owner_telegram_user_id: int, draft_id: int) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(PostDraft)
            .join(User, PostDraft.owner_id == User.id)
            .where(
                PostDraft.id == draft_id,
                User.telegram_user_id == owner_telegram_user_id,
                PostDraft.status == STATUS_PUBLISHING,
            )
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            return False
        now = datetime.now(timezone.utc)
        draft.status = STATUS_PUBLISHED
        draft.published_at = now
        draft.updated_at = now
        await session.commit()
        return True
