"""Stage 2: private file distribution, notices, throttles, handover requests."""
from alembic import op
import sqlalchemy as sa
from app import models

revision = '0002_stage2_integrations'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

NEW_TABLES = ['download_tickets','asset_shares','notifications','password_reset_tokens',
              'security_throttles','handover_fix_requests']


def upgrade():
    bind = op.get_bind()
    # 0001 bootstrapped from live ORM metadata in the legacy v0.1 project.
    # Fresh v0.3 installations may already contain these columns; historical
    # v0.1 installations may not. Inspect before changing existing schemas.
    inspect=sa.inspect(bind)
    if 'auth_version' not in {c['name'] for c in inspect.get_columns('users')}:
        op.add_column('users', sa.Column('auth_version', sa.Integer(), server_default='0', nullable=False))
    if 'malware_scan_status' not in {c['name'] for c in inspect.get_columns('listing_assets')}:
        op.add_column('listing_assets', sa.Column('malware_scan_status', sa.String(24), server_default='NOT_PERFORMED', nullable=False))
    for name in NEW_TABLES:
        models.Base.metadata.tables[name].create(bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    for name in reversed(NEW_TABLES):
        models.Base.metadata.tables[name].drop(bind, checkfirst=True)
    op.drop_column('listing_assets','malware_scan_status')
    op.drop_column('users','auth_version')
