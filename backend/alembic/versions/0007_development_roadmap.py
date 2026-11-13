"""Buyer development roadmaps after simulated handover.

Revision ID: 0007_development_roadmap
Revises: 0006_deal_management
"""
from alembic import op
from app import roadmap_models

revision = '0007_development_roadmap'
down_revision = '0006_deal_management'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for name in ('development_roadmaps', 'development_roadmap_tasks'):
        roadmap_models.Base.metadata.tables[name].create(bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in ('development_roadmap_tasks', 'development_roadmaps'):
        roadmap_models.Base.metadata.tables[name].drop(bind, checkfirst=True)
