from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.database import Base, Channel, SessionLocal, User


class ChannelAffiliateConfig(Base):
    __tablename__ = "channel_affiliate_configs"
    __table_args__ = (
        UniqueConstraint("channel_id", name="uq_channel_affiliate_config_channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"), nullable=False, unique=True, index=True
    )
    partner_tag: Mapped[str] = mapped_column(String(120), nullable=False)
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


def validate_partner_tag(value: str) -> str:
    tag = value.strip()
    if not tag or len(tag) > 120:
        raise ValueError("Tracking ID Amazon non valido.")
    if any(char.isspace() for char in tag):
        raise ValueError("Il Tracking ID non deve contenere spazi.")
    return tag


async def _owned_channel(session, owner_telegram_user_id: int, channel_id: int):
    result = await session.execute(
        select(Channel)
        .join(User, Channel.owner_id == User.id)
        .where(
            Channel.id == channel_id,
            User.telegram_user_id == owner_telegram_user_id,
            Channel.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def get_channel_partner_tag(
    owner_telegram_user_id: int,
    channel_id: int,
) -> str | None:
    async with SessionLocal() as session:
        channel = await _owned_channel(session, owner_telegram_user_id, channel_id)
        if channel is None:
            return None
        result = await session.execute(
            select(ChannelAffiliateConfig).where(
                ChannelAffiliateConfig.channel_id == channel.id
            )
        )
        config = result.scalar_one_or_none()
        return config.partner_tag if config else None


async def get_effective_partner_tag(
    owner_telegram_user_id: int,
    channel_id: int,
) -> str:
    custom = await get_channel_partner_tag(owner_telegram_user_id, channel_id)
    return custom or get_settings().amazon_partner_tag


async def set_channel_partner_tag(
    owner_telegram_user_id: int,
    channel_id: int,
    partner_tag: str,
) -> ChannelAffiliateConfig:
    partner_tag = validate_partner_tag(partner_tag)
    async with SessionLocal() as session:
        channel = await _owned_channel(session, owner_telegram_user_id, channel_id)
        if channel is None:
            raise ValueError("Canale non disponibile.")
        result = await session.execute(
            select(ChannelAffiliateConfig).where(
                ChannelAffiliateConfig.channel_id == channel.id
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            config = ChannelAffiliateConfig(
                channel_id=channel.id,
                partner_tag=partner_tag,
            )
            session.add(config)
        else:
            config.partner_tag = partner_tag
            config.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(config)
        return config


async def reset_channel_partner_tag(
    owner_telegram_user_id: int,
    channel_id: int,
) -> bool:
    async with SessionLocal() as session:
        channel = await _owned_channel(session, owner_telegram_user_id, channel_id)
        if channel is None:
            return False
        result = await session.execute(
            select(ChannelAffiliateConfig).where(
                ChannelAffiliateConfig.channel_id == channel.id
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            return True
        await session.delete(config)
        await session.commit()
        return True
