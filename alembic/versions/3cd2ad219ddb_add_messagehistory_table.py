"""Add MessageHistory table

Revision ID: 3cd2ad219ddb
Revises: aa4d1590bd69
Create Date: 2025-06-05 12:08:47.707116

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '3cd2ad219ddb'
down_revision: Union[str, None] = 'aa4d1590bd69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    # Drop FK constraint ONLY if it exists (safe for fresh DBs)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    fk_names = [fk['name'] for fk in inspector.get_foreign_keys('message_history')]
    if 'message_history_invoice_id_fkey' in fk_names:
        op.drop_constraint('message_history_invoice_id_fkey', 'message_history', type_='foreignkey')

    # Drop invoice_id column ONLY if it exists
    columns = [col['name'] for col in inspector.get_columns('message_history')]
    if 'invoice_id' in columns:
        op.drop_column('message_history', 'invoice_id')

    # Always (re-)add the new FK for client_id → client_contexts
    # Note: Name can be auto-generated, or specify one if you want.
    op.create_foreign_key(
        'fk_message_history_client_id',   # Give it a stable name for downgrade too
        'message_history',
        'client_contexts',
        ['client_id'],
        ['client_id'],
        ondelete='CASCADE'
    )

def downgrade() -> None:
    """Downgrade schema."""
    # Remove the new FK
    op.drop_constraint('fk_message_history_client_id', 'message_history', type_='foreignkey')

    # Add invoice_id column back if needed
    op.add_column('message_history', sa.Column('invoice_id', sa.INTEGER(), autoincrement=False, nullable=True))

    # Restore the old FK for invoice_id
    op.create_foreign_key(
        'message_history_invoice_id_fkey',
        'message_history',
        'invoice_contexts',
        ['invoice_id'],
        ['id'],
        ondelete='CASCADE'
    )
