def import_all_models() -> None:
    """Importa i moduli che dichiarano modelli SQLAlchemy.

    Necessario prima di create_all/Alembic così metadata conosce tutte le tabelle.
    """
    import app.database  # noqa: F401
    import app.autopost_store  # noqa: F401
    import app.autopost_runtime_store  # noqa: F401
    import app.autopost_queue_store  # noqa: F401
    import app.autopost_advanced_store  # noqa: F401
    import app.dedupe_store  # noqa: F401
    import app.scheduled_store  # noqa: F401
    import app.template_store  # noqa: F401
    import app.affiliate_store  # noqa: F401
    import app.analytics_store  # noqa: F401
    import app.shortlink_store  # noqa: F401
    import app.ai_store  # noqa: F401
    import app.drafts_store  # noqa: F401
