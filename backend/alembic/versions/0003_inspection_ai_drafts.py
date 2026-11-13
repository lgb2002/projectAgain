"""Seller-consented inspection access and on-demand AI listing assistance."""
from alembic import op
from app import models

revision = '0003_inspection_ai_drafts'
down_revision = '0002_stage2_integrations'
branch_labels = None
depends_on = None

def upgrade():
    bind=op.get_bind()
    for name in ('inspection_accesses','listing_ai_drafts'):
        models.Base.metadata.tables[name].create(bind, checkfirst=True)

def downgrade():
    bind=op.get_bind()
    for name in ('listing_ai_drafts','inspection_accesses'):
        models.Base.metadata.tables[name].drop(bind,checkfirst=True)
