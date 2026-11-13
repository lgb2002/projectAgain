"""Never run destructive integration fixtures against a user-supplied database.

Pytest loads conftest.py before test modules import app.db, so all test sessions
use an isolated temporary SQLite database even if Replit sets DATABASE_URL to
an actual PostgreSQL database. Do not import app.db before this module runs.
"""
import os
import secrets
import tempfile
from pathlib import Path

_tmpdir = tempfile.TemporaryDirectory(prefix='micro_asset_pytest_')
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(_tmpdir.name) / 'test.sqlite3')
os.environ['APP_ENV'] = 'test'
os.environ['GITHUB_CI_LOOKUP_DISABLED'] = '1'
os.environ['JWT_SECRET'] = secrets.token_urlsafe(48)


import pytest

@pytest.fixture(autouse=True)
def db_clean():
    # ONLY temp SQLite URL set above. Never use an externally supplied DB.
    from app.db import Base, engine
    from app import models, marketplace_models, deal_models, roadmap_models, v012_models, privacy, readiness_report
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
