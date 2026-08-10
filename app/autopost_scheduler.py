import asyncio
import logging
from datetime import timezone

from apscheduler.jobstores.base import (
    JobLookupError,
)
from apscheduler.schedulers import (
    SchedulerNotRunningError,
)
from apscheduler.schedulers.asyncio import (
    AsyncIOScheduler,
)

from app.autopost_pipeline import (
    run_channel_autopost_pipeline,
)
from app.autopost_runtime_store import (
    get_or_create_runtime_config,
    list_enabled_autopost_channels,
)
from app.autopost_store import (
    get_or_create_autopost_config,
)
from app.autoposting import (
    build_demo_products,
)


_scheduler: (
    AsyncIOScheduler | None
) = None


# =========================================================
# JOB ID
# =========================================================


def autopost_job_id(
    channel_id: int,
) -> str:
    return (
        f"autopost_scan_{channel_id}"
    )


# =========================================================
# SCAN
# =========================================================


async def run_autopost_scan(
    owner_telegram_user_id: int,
    channel_id: int,
) -> None:
    """
    Esegue UNA scansione.

    FASE 10B:
    - trova prodotti DEMO
    - esegue Pipeline 9
    - limita candidati
    - scrive risultato nei log

    NON pubblica.
    NON salva ancora candidati.
    """

    try:
        autopost_config = (
            await get_or_create_autopost_config(
                owner_telegram_user_id,
                channel_id,
            )
        )

        #
        # Se nel frattempo l'admin
        # ha spento Autoposting,
        # non facciamo nulla.
        #
        if not autopost_config.is_enabled:
            logging.info(
                "Autopost scan ignorato "
                "per canale %s: OFF.",
                channel_id,
            )

            return

        runtime = (
            await get_or_create_runtime_config(
                owner_telegram_user_id,
                channel_id,
            )
        )

        # ================================================
        # PROVIDER DEMO
        # ================================================

        products = (
            build_demo_products()
        )

        # ================================================
        # PIPELINE FASE 9
        # ================================================

        result = (
            await run_channel_autopost_pipeline(
                owner_telegram_user_id=(
                    owner_telegram_user_id
                ),
                channel_id=channel_id,
                products=products,
            )
        )

        #
        # Applichiamo il limite
        # configurato nella 10A.
        #
        candidates = (
            result.final_candidates[
                :int(
                    runtime
                    .max_candidates_per_scan
                )
            ]
        )

        logging.info(
            (
                "AUTOPOST SCAN | "
                "channel=%s | "
                "source=%s | "
                "categories=%s | "
                "filters=%s | "
                "deals=%s | "
                "duplicates=%s | "
                "final=%s | "
                "selected=%s"
            ),
            channel_id,
            result.source_count,
            result.category_passed_count,
            result.filter_passed_count,
            result.deal_valid_count,
            result.duplicate_count,
            result.final_count,
            len(candidates),
        )

        for index, candidate in enumerate(
            candidates,
            start=1,
        ):
            logging.info(
                (
                    "AUTOPOST CANDIDATE | "
                    "channel=%s | "
                    "rank=%s | "
                    "asin=%s | "
                    "score=%s | "
                    "title=%s"
                ),
                channel_id,
                index,
                candidate.product.asin,
                candidate.evaluation.score,
                candidate.product.title,
            )

    except Exception:
        logging.exception(
            "Errore Autopost scan "
            "canale %s.",
            channel_id,
        )


# =========================================================
# CREA / AGGIORNA JOB
# =========================================================


def schedule_autopost_channel(
    owner_telegram_user_id: int,
    channel_id: int,
    interval_minutes: int,
) -> None:
    if _scheduler is None:
        raise RuntimeError(
            "Autopost Scheduler "
            "non avviato."
        )

    _scheduler.add_job(
        run_autopost_scan,
        trigger="interval",
        minutes=int(
            interval_minutes
        ),
        args=[
            owner_telegram_user_id,
            channel_id,
        ],
        id=autopost_job_id(
            channel_id
        ),
        replace_existing=True,

        #
        # Esegue subito una prima
        # scansione all'avvio.
        #
        next_run_time=None,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    #
    # add_job con next_run_time=None
    # crea il job inizialmente pausato.
    #
    # Lo riattiviamo e impostiamo
    # la prima esecuzione immediata.
    #
    job = _scheduler.get_job(
        autopost_job_id(
            channel_id
        )
    )

    if job is not None:
        job.resume()

    logging.info(
        (
            "Autopost job registrato | "
            "channel=%s | "
            "interval=%s min"
        ),
        channel_id,
        interval_minutes,
    )


# =========================================================
# VERSIONE SICURA CON PRIMA SCANSIONE
# =========================================================


async def register_autopost_channel(
    owner_telegram_user_id: int,
    channel_id: int,
    interval_minutes: int,
    run_now: bool = True,
) -> None:
    """
    Registra il job periodico.

    Se run_now=True fa anche
    una scansione immediata.
    """

    if _scheduler is None:
        raise RuntimeError(
            "Autopost Scheduler "
            "non avviato."
        )

    _scheduler.add_job(
        run_autopost_scan,
        trigger="interval",
        minutes=int(
            interval_minutes
        ),
        args=[
            owner_telegram_user_id,
            channel_id,
        ],
        id=autopost_job_id(
            channel_id
        ),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    logging.info(
        (
            "Autopost job attivo | "
            "channel=%s | "
            "interval=%s min"
        ),
        channel_id,
        interval_minutes,
    )

    if run_now:
        await run_autopost_scan(
            owner_telegram_user_id,
            channel_id,
        )


# =========================================================
# RIMUOVI JOB
# =========================================================


def remove_autopost_channel(
    channel_id: int,
) -> None:
    if _scheduler is None:
        return

    try:
        _scheduler.remove_job(
            autopost_job_id(
                channel_id
            )
        )

    except JobLookupError:
        pass

    logging.info(
        "Autopost job rimosso | "
        "channel=%s",
        channel_id,
    )


# =========================================================
# REFRESH SINGOLO CANALE
# =========================================================


async def refresh_autopost_channel(
    owner_telegram_user_id: int,
    channel_id: int,
) -> None:
    """
    Chiamata quando l'admin:
    - attiva/disattiva autopost
    - cambia intervallo scansione
    """

    config = (
        await get_or_create_autopost_config(
            owner_telegram_user_id,
            channel_id,
        )
    )

    if not config.is_enabled:
        remove_autopost_channel(
            channel_id
        )

        return

    runtime = (
        await get_or_create_runtime_config(
            owner_telegram_user_id,
            channel_id,
        )
    )

    await register_autopost_channel(
        owner_telegram_user_id=(
            owner_telegram_user_id
        ),
        channel_id=channel_id,
        interval_minutes=int(
            runtime
            .scan_interval_minutes
        ),
        run_now=False,
    )


# =========================================================
# START
# =========================================================


async def start_autopost_scheduler(
) -> None:
    global _scheduler

    if _scheduler is not None:
        return

    loop = (
        asyncio.get_running_loop()
    )

    _scheduler = AsyncIOScheduler(
        event_loop=loop,
        timezone=timezone.utc,
    )

    _scheduler.start()

    enabled_channels = (
        await list_enabled_autopost_channels()
    )

    for channel in enabled_channels:
        await register_autopost_channel(
            owner_telegram_user_id=(
                channel
                .owner_telegram_user_id
            ),
            channel_id=(
                channel.channel_id
            ),
            interval_minutes=(
                channel
                .scan_interval_minutes
            ),
            run_now=True,
        )

    logging.info(
        (
            "Autopost Scheduler avviato. "
            "%s canali attivi."
        ),
        len(enabled_channels),
    )


# =========================================================
# STOP
# =========================================================


def stop_autopost_scheduler(
) -> None:
    global _scheduler

    if _scheduler is None:
        return

    try:
        _scheduler.shutdown(
            wait=False
        )

    except SchedulerNotRunningError:
        pass

    _scheduler = None

    logging.info(
        "Autopost Scheduler fermato."
    )
