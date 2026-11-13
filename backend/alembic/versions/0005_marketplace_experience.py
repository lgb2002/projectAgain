"""v0.7 showcase, questions, notification preferences, email outbox.

Revision ID: 0005_marketplace_experience
Revises: 0004_project_imports
"""
from alembic import op
from app import marketplace_models

revision = '0005_marketplace_experience'
down_revision = '0004_project_imports'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for table in ('listing_showcases', 'listing_media', 'listing_inquiries', 'notification_preferences', 'notification_emails'):
        marketplace_models.Base.metadata.tables[table].create(bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for table in ('notification_emails', 'notification_preferences', 'listing_inquiries', 'listing_media', 'listing_showcases'):
        marketplace_models.Base.metadata.tables[table].drop(bind, checkfirst=True)
