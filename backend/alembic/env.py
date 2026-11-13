from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from app.db import Base, database_url
from app import models, marketplace_models, deal_models, roadmap_models, v012_models, privacy, readiness_report
config = context.config
if config.config_file_name is not None: fileConfig(config.config_file_name)
config.set_main_option('sqlalchemy.url', database_url().replace('%', '%%'))
target_metadata = Base.metadata

def offline():
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True, dialect_opts={'paramstyle':'named'})
    with context.begin_transaction():context.run_migrations()

def online():
    engine = engine_from_config(config.get_section(config.config_ini_section,{}), prefix='sqlalchemy.', poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn,target_metadata=target_metadata)
        with context.begin_transaction():context.run_migrations()

if context.is_offline_mode(): offline()
else: online()
