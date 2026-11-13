"""v0.13: privacy erasure and always-generated handover readiness reports.

Revision ID: 0009_privacy_readiness
Revises: 0008_integrated_workspace
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from alembic import op
import sqlalchemy as sa
from app import privacy, readiness_report

revision='0009_privacy_readiness'
down_revision='0008_integrated_workspace'
branch_labels=None
depends_on=None


def upgrade():
    bind=op.get_bind()
    if 'deleted_at' not in {c['name'] for c in sa.inspect(bind).get_columns('users')}:
        with op.batch_alter_table('users') as batch:
            batch.add_column(sa.Column('deleted_at',sa.DateTime(timezone=True),nullable=True))
    for name in ('listing_readiness_reports','privacy_erasures','privacy_erasure_objects'):
        readiness_report.Base.metadata.tables[name].create(bind,checkfirst=True)
    # Backfill all pre-existing v0.12 listings, including manual and private drafts.
    listing=sa.Table('listings',sa.MetaData(),autoload_with=bind)
    summary=sa.Table('listing_source_summaries',sa.MetaData(),autoload_with=bind)
    target=readiness_report.Base.metadata.tables['listing_readiness_reports']
    sources=dict(bind.execute(sa.select(summary.c.listing_id,summary.c.analysis)).all())
    for row in bind.execute(sa.select(listing)).mappings():
        exists=bind.execute(sa.select(target.c.listing_id).where(target.c.listing_id==row['id'])).scalar_one_or_none()
        if exists is not None:continue
        report=readiness_report.make_report(SimpleNamespace(**row),sources.get(row['id']))
        bind.execute(target.insert().values(listing_id=row['id'],report=report,
                        report_version='readiness-v3',generated_at=datetime.now(timezone.utc)))


def downgrade():
    raise RuntimeError('v0.13 privacy/erasure records must not be lost; restore approved backup instead.')
