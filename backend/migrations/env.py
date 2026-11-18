from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
import app.models  # noqa: registers all tables
from app.core.db import Base
from app.core.config import settings

config = context.config
if config.config_file_name: fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_online():
    cfg = config.get_section(config.config_ini_section) or {}
    engine = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction(): context.run_migrations()


run_migrations_online()
