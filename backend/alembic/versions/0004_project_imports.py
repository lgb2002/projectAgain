"""Private GitHub App connections, ZIP/GitHub staging and safe reports."""
from alembic import op
from app import models

revision = '0004_project_imports'
down_revision = '0003_inspection_ai_drafts'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    for name in ('github_connections', 'project_imports', 'listing_source_summaries'):
        models.Base.metadata.tables[name].create(bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in ('listing_source_summaries', 'project_imports', 'github_connections'):
        models.Base.metadata.tables[name].drop(bind, checkfirst=True)
