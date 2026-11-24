"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-24 15:31:53.455345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'instances',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('profile', sa.String(), nullable=False),
        sa.Column('auth', sa.String(), nullable=False),
        sa.Column('availability', sa.String(), nullable=False),
        sa.Column('credits', sa.Integer(), nullable=True),
        sa.Column('credit_source', sa.String(), nullable=True),
        sa.Column('checked_at', sa.String(), nullable=True),
        sa.Column('error', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile')
    )
    op.create_table(
        'projects',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('language', sa.String(), nullable=False),
        sa.Column('duration', sa.Integer(), nullable=True),
        sa.Column('ratio', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('instance_id', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False),
        sa.Column('settings', sa.JSON(), nullable=False),
        sa.Column('references', sa.JSON(), nullable=False),
        sa.Column('remote_id', sa.String(), nullable=True),
        sa.Column('error', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['instance_id'], ['instances.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_projects_status'), ['status'], unique=False)

    op.create_table(
        'logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('at', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(length=32), nullable=True),
        sa.Column('scene_id', sa.String(), nullable=True),
        sa.Column('attempt_id', sa.String(), nullable=True),
        sa.Column('instance_id', sa.String(), nullable=True),
        sa.Column('event', sa.String(), nullable=False),
        sa.Column('detail', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_logs_project_id'), ['project_id'], unique=False)

    op.create_table(
        'scenes',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('project_id', sa.String(length=32), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('prompt', sa.String(), nullable=False),
        sa.Column('duration', sa.Integer(), nullable=True),
        sa.Column('references', sa.JSON(), nullable=False),
        sa.Column('continuity', sa.String(), nullable=False),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('remote_id', sa.String(), nullable=True),
        sa.Column('files', sa.JSON(), nullable=False),
        sa.Column('dependencies', sa.JSON(), nullable=False),
        sa.Column('selected_attempt', sa.String(), nullable=True),
        sa.Column('stale', sa.Boolean(), nullable=False),
        sa.Column('error', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'order')
    )
    op.create_table(
        'attempts',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('scene_id', sa.String(length=32), nullable=False),
        sa.Column('instance_id', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('remote_id', sa.String(), nullable=True),
        sa.Column('evidence', sa.String(), nullable=True),
        sa.Column('files', sa.JSON(), nullable=False),
        sa.Column('dependencies', sa.JSON(), nullable=False),
        sa.Column('error', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['instance_id'], ['instances.id'], ),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('attempts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_attempts_scene_id'), ['scene_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('attempts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_attempts_scene_id'))

    op.drop_table('attempts')
    op.drop_table('scenes')
    with op.batch_alter_table('logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_logs_project_id'))

    op.drop_table('logs')
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_projects_status'))

    op.drop_table('projects')
    op.drop_table('instances')
