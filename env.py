"""
Alembic migrations environment configuration.
This module handles both online and offline database migrations.
"""

from alembic import context
from logging.config import fileConfig
import os
import sys
from typing import Optional

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    # Import Base metadata and database configuration
    from models import Base
    from database import DATABASE_URL
except ImportError as e:
    raise ImportError(f"Failed to import required modules: {str(e)}")

# Alembic Config object
config = context.config

# Set database URL in Alembic config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Configure Python logging
fileConfig(config.config_file_name)

# Set target metadata for migrations
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    
    This allows running migrations without requiring a database connection.
    Returns directly-rendered SQL.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    
    Runs migrations with an active database connection.
    """
    try:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
            )

            with context.begin_transaction():
                context.run_migrations()
    except SQLAlchemyError as e:
        raise Exception(f"Failed to run online migrations: {str(e)}")

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String  # Import what you need

Base = declarative_base()

# Define your models here
class YourModel(Base):
    __tablename__ = 'your_table'
    # Define your columns