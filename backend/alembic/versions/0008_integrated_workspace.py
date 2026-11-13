"""Add v0.12 negotiation, personal context, and support (data-preserving).

Revision ID: 0008_integrated_workspace
Revises: 0007_development_roadmap
"""
from uuid import uuid4
from alembic import op
import sqlalchemy as sa
from app import v012_models

revision = '0008_integrated_workspace'
down_revision = '0007_development_roadmap'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # 0001_initial builds from current metadata on fresh installs. Existing v0.11
    # databases lack these columns. Only apply the columns that are actually absent.
    inspector = sa.inspect(bind)
    required = {
        'offers': [('thread_id', sa.String(36)), ('listing_version_at_proposal', sa.Integer())],
        'transactions': [('completed_at', sa.DateTime(timezone=True))],
        'development_roadmap_tasks': [('blocked_reason', sa.String(28))],
    }
    for table, columns in required.items():
        existing={c['name'] for c in inspector.get_columns(table)}
        for name, typ in columns:
            if name not in existing:
                with op.batch_alter_table(table) as batch:
                    batch.add_column(sa.Column(name, typ, nullable=True))
    for name in ('offer_threads', 'support_policy_snapshots', 'support_cases',
                 'support_messages', 'roadmap_buyer_contexts', 'roadmap_task_help_links'):
        v012_models.Base.metadata.tables[name].create(bind, checkfirst=True)
    offers = sa.table('offers', sa.column('id', sa.String), sa.column('parent_offer_id', sa.String),
                      sa.column('listing_id', sa.String), sa.column('buyer_id', sa.String),
                      sa.column('seller_id', sa.String), sa.column('status', sa.String),
                      sa.column('thread_id', sa.String), sa.column('created_at', sa.DateTime),
                      sa.column('version', sa.Integer))
    old = bind.execute(sa.select(offers)).mappings().all()
    by_id = {row['id']: row for row in old}
    groups = {}
    for row in old:
        root = row['id']; seen = set()
        while by_id.get(root) and by_id[root]['parent_offer_id'] and root not in seen:
            seen.add(root); root = by_id[root]['parent_offer_id']
        groups.setdefault(root, []).append(row)
    threads = v012_models.Base.metadata.tables['offer_threads']
    for group in groups.values():
        group.sort(key=lambda r: (str(r['created_at']), r['id']))
        first, last = group[0], group[-1]
        state = last['status'] if last['status'] != 'PENDING' else 'UNRESOLVED'
        thread_id = str(uuid4())
        bind.execute(threads.insert().values(id=thread_id, listing_id=first['listing_id'],
            buyer_id=first['buyer_id'], seller_id=first['seller_id'], status=state,
            last_offer_id=last['id'], opened_at=first['created_at'],
            last_activity_at=last['created_at'], version=len(group), is_demo=True))
        bind.execute(offers.update().where(offers.c.id.in_([r['id'] for r in group])).values(thread_id=thread_id))
    # This migration never changes listing status: old RESERVED/CLOSED may be legitimate.
    # Detach obsolete DEMO inventory locks only. Audit flagged listings before manual repair.
    bind.execute(sa.text('UPDATE transactions SET exclusive_guard_listing_id = NULL WHERE is_demo = :demo AND exclusive_guard_listing_id IS NOT NULL'), {'demo': True})


def downgrade():
    raise RuntimeError('v0.12 downgrade intentionally blocked to protect negotiation/support records; restore an approved backup instead.')
