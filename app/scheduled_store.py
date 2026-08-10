import json
from datetime import (
    datetime,
    timezone,
)

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.amazon.models import (
    ProductSnapshot,
)
from app.database import (
    Base,
    Channel,
    SessionLocal,
    User,
)


STATUS_PENDING = "pending"
STATUS_PUBLISHED = "published"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"


class ScheduledPost(Base):
    __tablename__ = (
        "scheduled_posts"
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"),
        nullable=False,
        index=True,
    )

    run_at: Mapped[datetime] = (
        mapped_column(
            DateTime(timezone=True),
            nullable=False,
            index=True,
        )
    )

    # Snapshot completo del prodotto.
    product_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
        )
    )

    # Testo già renderizzato.
    #
    # Se cambi template dopo aver
    # programmato il post, questo
    # post resterà identico.
    post_text: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
        )
    )

    status: Mapped[str] = (
        mapped_column(
            String(30),
            default=STATUS_PENDING,
            nullable=False,
            index=True,
        )
    )

    error_message: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(
            timezone.utc
        ),
        nullable=False,
    )

    updated_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(
            timezone.utc
        ),
        onupdate=lambda: datetime.now(
            timezone.utc
        ),
        nullable=False,
    )

    published_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


async def create_scheduled_post(
    owner_telegram_user_id: int,
    channel_id: int,
    run_at_utc: datetime,
    product: ProductSnapshot,
    post_text: str,
) -> ScheduledPost:
    async with SessionLocal() as session:
        owner_result = (
            await session.execute(
                select(User).where(
                    User.telegram_user_id
                    == (
                        owner_telegram_user_id
                    )
                )
            )
        )

        owner = (
            owner_result
            .scalar_one_or_none()
        )

        if owner is None:
            raise ValueError(
                "Utente non registrato."
            )

        channel_result = (
            await session.execute(
                select(Channel).where(
                    Channel.id
                    == channel_id,
                    Channel.owner_id
                    == owner.id,
                    Channel.is_active
                    .is_(True),
                )
            )
        )

        channel = (
            channel_result
            .scalar_one_or_none()
        )

        if channel is None:
            raise ValueError(
                "Canale non disponibile."
            )

        if run_at_utc.tzinfo is None:
            run_at_utc = (
                run_at_utc.replace(
                    tzinfo=timezone.utc
                )
            )

        else:
            run_at_utc = (
                run_at_utc.astimezone(
                    timezone.utc
                )
            )

        product_json = json.dumps(
            product.model_dump(
                mode="json"
            ),
            ensure_ascii=False,
        )

        scheduled_post = (
            ScheduledPost(
                owner_id=owner.id,
                channel_id=channel.id,
                run_at=run_at_utc,
                product_json=(
                    product_json
                ),
                post_text=post_text,
                status=STATUS_PENDING,
            )
        )

        session.add(
            scheduled_post
        )

        await session.commit()

        await session.refresh(
            scheduled_post
        )

        return scheduled_post


async def list_pending_scheduled_posts(
) -> list[ScheduledPost]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(ScheduledPost)
            .where(
                ScheduledPost.status
                == STATUS_PENDING
            )
            .order_by(
                ScheduledPost.run_at
            )
        )

        return list(
            result.scalars().all()
        )


async def get_scheduled_delivery(
    post_id: int,
) -> tuple[
    ScheduledPost,
    Channel,
] | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(
                ScheduledPost,
                Channel,
            )
            .join(
                Channel,
                ScheduledPost.channel_id
                == Channel.id,
            )
            .where(
                ScheduledPost.id
                == post_id
            )
        )

        row = result.first()

        if row is None:
            return None

        return (
            row[0],
            row[1],
        )


async def mark_scheduled_published(
    post_id: int,
) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(ScheduledPost).where(
                ScheduledPost.id
                == post_id
            )
        )

        post = (
            result.scalar_one_or_none()
        )

        if post is None:
            return

        post.status = STATUS_PUBLISHED

        post.published_at = (
            datetime.now(
                timezone.utc
            )
        )

        post.updated_at = (
            datetime.now(
                timezone.utc
            )
        )

        post.error_message = None

        await session.commit()


async def mark_scheduled_failed(
    post_id: int,
    error_message: str,
) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(ScheduledPost).where(
                ScheduledPost.id
                == post_id
            )
        )

        post = (
            result.scalar_one_or_none()
        )

        if post is None:
            return

        post.status = STATUS_FAILED

        post.error_message = (
            error_message[:2000]
        )

        post.updated_at = (
            datetime.now(
                timezone.utc
            )
        )

        await session.commit()
