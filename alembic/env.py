import asyncio
from logging.config import fileConfig

# Изменено: используем create_engine для синхронного движка Alembic
from sqlalchemy import engine_from_config, create_engine
from sqlalchemy import pool
# Удален импорт AsyncEngine, так как он не будет использоваться для Alembic
# from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import context

# Это строка для импорта вашего Base из models.py
# Убедитесь, что путь правильный относительно места запуска Alembic (корня проекта)
import sys
import os
# Добавляем корневую директорию проекта в sys.path
# Это необходимо, чтобы Alembic мог найти ваш models.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models import Base # Импортируем ваш Base класс

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata # <-- Убедитесь, что эта строка НЕ закомментирована и правильно указывает на Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired here.
# Например, URL базы данных из alembic.ini

def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

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


# Изменено: do_run_migrations теперь принимает синхронное соединение
def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True, # Важно для autogenerate, чтобы сравнивать типы колонок
    )

    with context.begin_transaction():
        context.run_migrations()

# Изменено: run_migrations_online теперь синхронная и использует create_engine
def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Изменено: используем create_engine вместо AsyncEngine
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # future=True # Удалено: future=True используется с AsyncEngine
    )

    # Изменено: используем синхронное соединение
    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    # Изменено: вызываем синхронную функцию напрямую
    run_migrations_online()
