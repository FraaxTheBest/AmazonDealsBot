from __future__ import annotations

import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, Channel, SessionLocal, User


ALPHABET = string.ascii_letters + string.digits


class ShortLink(Base):
    __tablename__ = "short_links"
    __table_args__ = (
        UniqueConstraint("code", name="uq_short_links_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    asin: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    destination_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


class ShortLinkClick(Base):
    __tablename__ = "short_link_clicks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    short_link_id: Mapped[int] = mapped_column(
        ForeignKey("short_links.id"), nullable=False, index=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    referer: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


@dataclass(frozen=True, slots=True)
class ShortLinkStats:
    links: int
    clicks: int


def _new_code(length: int = 8) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


async def _owner_and_channel(
    session,
    owner_telegram_user_id: int,
    channel_id: int,
):
    result = await session.execute(
        select(User, Channel)
        .join(Channel, Channel.owner_id == User.id)
        .where(
            User.telegram_user_id == owner_telegram_user_id,
            Channel.id == channel_id,
            Channel.is_active.is_(True),
        )
    )
    row = result.first()
    return (row[0], row[1]) if row else None


async def create_or_get_shortlink(
    *,
    owner_telegram_user_id: int,
    channel_id: int,
    destination_url: str,
    asin: str | None = None,
) -> ShortLink:
    destination = destination_url.strip()
    if not destination.startswith(("https://", "http://")):
        raise ValueError("Destinazione shortlink non valida.")

    async with SessionLocal() as session:
        owned = await _owner_and_channel(
            session,
            owner_telegram_user_id,
            channel_id,
        )
        if owned is None:
            raise ValueError("Canale non disponibile.")
        owner, channel = owned

        result = await session.execute(
            select(ShortLink).where(
                ShortLink.owner_id == owner.id,
                ShortLink.channel_id == channel.id,
                ShortLink.destination_url == destination,
                ShortLink.is_active.is_(True),
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        for _ in range(10):
            code = _new_code()
            check = await session.execute(select(ShortLink.id).where(ShortLink.code == code))
            if check.scalar_one_or_none() is None:
                break
        else:
            raise RuntimeError("Impossibile generare shortlink univoco.")

        link = ShortLink(
            owner_id=owner.id,
            channel_id=channel.id,
            code=code,
            asin=(asin.strip().upper() if asin else None),
            destination_url=destination,
            is_active=True,
        )
        session.add(link)
        await session.commit()
        await session.refresh(link)
        return link


async def resolve_shortlink(code: str) -> ShortLink | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(ShortLink).where(
                ShortLink.code == code,
                ShortLink.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()


async def record_shortlink_click(
    short_link_id: int,
    *,
    user_agent: str | None = None,
    referer: str | None = None,
) -> None:
    async with SessionLocal() as session:
        session.add(
            ShortLinkClick(
                short_link_id=short_link_id,
                user_agent=(user_agent[:500] if user_agent else None),
                referer=(referer[:1000] if referer else None),
            )
        )
        await session.commit()


async def get_shortlink_stats(owner_telegram_user_id: int) -> ShortLinkStats:
    async with SessionLocal() as session:
        owner_result = await session.execute(
            select(User).where(User.telegram_user_id == owner_telegram_user_id)
        )
        owner = owner_result.scalar_one_or_none()
        if owner is None:
            return ShortLinkStats(0, 0)

        links_stmt = select(func.count()).select_from(ShortLink).where(
            ShortLink.owner_id == owner.id
        )
        links = int((await session.execute(links_stmt)).scalar_one())

        clicks_stmt = (
            select(func.count())
            .select_from(ShortLinkClick)
            .join(ShortLink, ShortLinkClick.short_link_id == ShortLink.id)
            .where(ShortLink.owner_id == owner.id)
        )
        clicks = int((await session.execute(clicks_stmt)).scalar_one())
        return ShortLinkStats(links, clicks)
