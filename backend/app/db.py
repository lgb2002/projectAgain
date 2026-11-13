import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def database_url():
    url = os.getenv('DATABASE_URL', 'sqlite:///./marketplace_dev.sqlite3')
    if url.startswith('postgres://'):
        url = 'postgresql+psycopg://' + url[len('postgres://'):]
    if url.startswith('postgresql://'):
        url = 'postgresql+psycopg://' + url[len('postgresql://'):]
    return url


class Base(DeclarativeBase):
    pass


URL = database_url()
if os.getenv('APP_ENV', 'development') == 'production' and URL.startswith('sqlite'):
    raise RuntimeError('Production requires PostgreSQL DATABASE_URL')
engine = create_engine(URL, pool_pre_ping=True, connect_args={'check_same_thread': False} if URL.startswith('sqlite') else {}, **({} if URL.startswith('sqlite') else {'pool_size': int(os.getenv('DB_POOL_SIZE', '2')), 'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', '1')), 'pool_timeout': 10, 'pool_recycle': 300}))
if URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def _fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
