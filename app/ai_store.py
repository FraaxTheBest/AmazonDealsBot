from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from app.config import get_settings
from app.database import Base, SessionLocal, User


class AIConfig(Base):
    __tablename__ = "ai_configs"
    __table_args__ = (
        UniqueConstraint("owner_id", name="uq_ai_config_owner"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="gpt-5")
    max_title_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    generate_description: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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


async def get_or_create_ai_config(owner_telegram_user_id: int) -> AIConfig:
    settings = get_settings()
    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(User.telegram_user_id == owner_telegram_user_id)
        )
        owner = result.scalar_one_or_none()
        if owner is None:
            raise ValueError("Utente non registrato.")

        result = await session.execute(
            select(AIConfig).where(AIConfig.owner_id == owner.id)
        )
        config = result.scalar_one_or_none()
        if config is None:
            config = AIConfig(
                owner_id=owner.id,
                enabled=bool(settings.ai_enabled),
                model=settings.openai_model,
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)
        return config


async def set_ai_enabled(owner_telegram_user_id: int, enabled: bool) -> AIConfig:
    await get_or_create_ai_config(owner_telegram_user_id)
    async with SessionLocal() as session:
        result = await session.execute(
            select(AIConfig)
            .join(User, AIConfig.owner_id == User.id)
            .where(User.telegram_user_id == owner_telegram_user_id)
        )
        config = result.scalar_one()
        config.enabled = bool(enabled)
        config.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(config)
        return config
