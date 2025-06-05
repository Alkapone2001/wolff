from logging.config import fileConfig
import os
import sys
from alembic import context
from sqlalchemy import engine_from_config, pool

# Add your project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import models + metadata
from models import Base
from models import ClientContext, InvoiceContext  # needed for autogenerate
from database import DATABASE_URL

# Alembic Config object
config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Logging setup
if config.config_file_name:
    fileConfig(config.config_file_name)

# Set target metadata for migrations
target_metadata = Base.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
