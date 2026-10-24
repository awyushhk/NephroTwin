from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from api.database import Base, database_url
from api import models  # noqa: F401 register tables

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", database_url().render_as_string(hide_password=False).replace("%", "%%"))
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=database_url().render_as_string(hide_password=False), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config({"sqlalchemy.url": database_url().render_as_string(hide_password=False)}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction(): context.run_migrations()
    connectable.dispose()

run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
