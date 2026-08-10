from dataclasses import dataclass


@dataclass(
    frozen=True,
    slots=True,
)
class EnabledAutopostChannel:
    owner_telegram_user_id: int

    channel_id: int

    channel_title: str

    scan_interval_minutes: int

    publish_interval_minutes: int

    max_candidates_per_scan: int


async def list_enabled_autopost_channels(
) -> list[
    EnabledAutopostChannel
]:
    """
    Restituisce tutti i canali
    con Autoposting ON.

    Utilizzato all'avvio
    dello scheduler Autopost.
    """

    async with SessionLocal() as session:
        result = await session.execute(
            select(
                ChannelAutopostConfig,
                ChannelAutopostRuntimeConfig,
                Channel,
                User,
            )
            .join(
                Channel,
                ChannelAutopostConfig
                .channel_id
                == Channel.id,
            )
            .join(
                User,
                Channel.owner_id
                == User.id,
            )
            .outerjoin(
                ChannelAutopostRuntimeConfig,
                ChannelAutopostRuntimeConfig
                .channel_id
                == Channel.id,
            )
            .where(
                ChannelAutopostConfig
                .is_enabled
                .is_(True),
                Channel.is_active
                .is_(True),
            )
        )

        rows = result.all()

        enabled: list[
            EnabledAutopostChannel
        ] = []

        for (
            autopost_config,
            runtime_config,
            channel,
            user,
        ) in rows:
            if runtime_config is None:
                runtime_config = (
                    ChannelAutopostRuntimeConfig(
                        channel_id=channel.id
                    )
                )

                session.add(
                    runtime_config
                )

                await session.flush()

            enabled.append(
                EnabledAutopostChannel(
                    owner_telegram_user_id=(
                        user.telegram_user_id
                    ),
                    channel_id=channel.id,
                    channel_title=(
                        channel.title
                    ),
                    scan_interval_minutes=int(
                        runtime_config
                        .scan_interval_minutes
                    ),
                    publish_interval_minutes=int(
                        runtime_config
                        .publish_interval_minutes
                    ),
                    max_candidates_per_scan=int(
                        runtime_config
                        .max_candidates_per_scan
                    ),
                )
            )

        await session.commit()

        return enabled
