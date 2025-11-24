# Import Flask app and models
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import flask_backend.models  # noqa: F401, E402 - Import models to register them
from flask_backend.db import Base, engine  # noqa: E402
from flask_backend.env_config import DATABASE_URL  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the SQLAlchemy URL from our config
config.set_main_option("sqlalchemy.url", str(DATABASE_URL))

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Executa migrações em modo 'offline'.

    Isso configura o contexto apenas com uma URL
    e não um Engine, embora um Engine seja aceitável
    aqui também. Ao pular a criação do Engine
    não precisamos nem de um DBAPI disponível.

    Chamadas para context.execute() aqui emitem a string fornecida para a
    saída do script.

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
    """Executa migrações em modo 'online'.

    Neste cenário precisamos criar um Engine
    e associar uma conexão com o contexto.

    Usamos o engine existente de flask_backend.db para manter
    consistência com a aplicação.
    """
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
