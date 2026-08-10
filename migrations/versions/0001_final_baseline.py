"""Baseline completa AmazonDealsBot.

Per database SQLite già esistente usare SOLO:
    alembic stamp 0001_final_baseline

Per database nuovo/PostgreSQL:
    alembic upgrade head
"""
from alembic import op

from app.database import Base
from app.model_registry import import_all_models


revision = "0001_final_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    import_all_models()
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    import_all_models()
    Base.metadata.drop_all(bind=op.get_bind())
