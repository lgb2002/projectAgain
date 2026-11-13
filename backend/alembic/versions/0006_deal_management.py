"""DEMO agreements, cancellations, disputes and timeline.

Revision ID: 0006_deal_management
Revises: 0005_marketplace_experience
"""
from alembic import op
from app import deal_models

revision = '0006_deal_management'
down_revision = '0005_marketplace_experience'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for name in ('deal_agreements', 'deal_cancellations', 'deal_disputes', 'deal_events'):
        deal_models.Base.metadata.tables[name].create(bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in ('deal_events', 'deal_disputes', 'deal_cancellations', 'deal_agreements'):
        deal_models.Base.metadata.tables[name].drop(bind, checkfirst=True)
