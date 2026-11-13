"""Initial schema generated from reviewed ORM metadata."""
from alembic import op
from app.db import Base
from app import models
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Initial bootstrap; subsequent changes must use explicit ALTER migrations.
    Base.metadata.create_all(bind=op.get_bind())

def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
