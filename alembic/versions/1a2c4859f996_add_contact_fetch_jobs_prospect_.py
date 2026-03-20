"""add_contact_fetch_jobs_prospect_contacts_title_match_rules

Revision ID: 1a2c4859f996
Revises: a1b2c3d4e5f7
Create Date: 2026-03-20 22:40:40.962225

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1a2c4859f996'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('title_match_rules',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('rule_type', sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False),
    sa.Column('keywords', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_title_match_rules_created_at'), 'title_match_rules', ['created_at'], unique=False)
    op.create_index(op.f('ix_title_match_rules_id'), 'title_match_rules', ['id'], unique=False)
    op.create_index(op.f('ix_title_match_rules_rule_type'), 'title_match_rules', ['rule_type'], unique=False)

    op.create_table('contact_fetch_jobs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('state', sa.Enum('queued', 'running', 'succeeded', 'failed', 'dead', name='contactfetchjobstate'), nullable=False),
    sa.Column('terminal_state', sa.Boolean(), nullable=False),
    sa.Column('attempt_count', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('last_error_code', sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True),
    sa.Column('last_error_message', sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=True),
    sa.Column('lock_token', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
    sa.Column('lock_expires_at', sa.DateTime(), nullable=True),
    sa.Column('contacts_found', sa.Integer(), nullable=False),
    sa.Column('title_matched_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contact_fetch_jobs_company_id'), 'contact_fetch_jobs', ['company_id'], unique=False)
    op.create_index(op.f('ix_contact_fetch_jobs_created_at'), 'contact_fetch_jobs', ['created_at'], unique=False)
    op.create_index(op.f('ix_contact_fetch_jobs_id'), 'contact_fetch_jobs', ['id'], unique=False)
    op.create_index(op.f('ix_contact_fetch_jobs_lock_expires_at'), 'contact_fetch_jobs', ['lock_expires_at'], unique=False)
    op.create_index(op.f('ix_contact_fetch_jobs_state'), 'contact_fetch_jobs', ['state'], unique=False)
    op.create_index(op.f('ix_contact_fetch_jobs_updated_at'), 'contact_fetch_jobs', ['updated_at'], unique=False)
    # Partial unique index: only one active (non-terminal) job per company at a time
    op.create_index(
        'uq_contact_fetch_jobs_company_active',
        'contact_fetch_jobs',
        ['company_id'],
        unique=True,
        postgresql_where=sa.text('terminal_state = false'),
    )

    op.create_table('prospect_contacts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('contact_fetch_job_id', sa.Uuid(), nullable=False),
    sa.Column('source', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
    sa.Column('first_name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('last_name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
    sa.Column('title_match', sa.Boolean(), nullable=False),
    sa.Column('linkedin_url', sqlmodel.sql.sqltypes.AutoString(length=2048), nullable=True),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
    sa.Column('email_status', sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
    sa.Column('snov_confidence', sa.Float(), nullable=True),
    sa.Column('snov_prospect_raw', sa.JSON(), nullable=True),
    sa.Column('snov_email_raw', sa.JSON(), nullable=True),
    sa.Column('zerobounce_raw', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['contact_fetch_job_id'], ['contact_fetch_jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prospect_contacts_company_id'), 'prospect_contacts', ['company_id'], unique=False)
    op.create_index(op.f('ix_prospect_contacts_contact_fetch_job_id'), 'prospect_contacts', ['contact_fetch_job_id'], unique=False)
    op.create_index(op.f('ix_prospect_contacts_created_at'), 'prospect_contacts', ['created_at'], unique=False)
    op.create_index(op.f('ix_prospect_contacts_email'), 'prospect_contacts', ['email'], unique=False)
    op.create_index(op.f('ix_prospect_contacts_email_status'), 'prospect_contacts', ['email_status'], unique=False)
    op.create_index(op.f('ix_prospect_contacts_id'), 'prospect_contacts', ['id'], unique=False)
    op.create_index(op.f('ix_prospect_contacts_title_match'), 'prospect_contacts', ['title_match'], unique=False)
    # Partial unique index: one email per company (NULL emails are allowed as duplicates)
    op.create_index(
        'uq_prospect_contacts_company_email',
        'prospect_contacts',
        ['company_id', 'email'],
        unique=True,
        postgresql_where=sa.text('email IS NOT NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_prospect_contacts_company_email', table_name='prospect_contacts')
    op.drop_index(op.f('ix_prospect_contacts_title_match'), table_name='prospect_contacts')
    op.drop_index(op.f('ix_prospect_contacts_id'), table_name='prospect_contacts')
    op.drop_index(op.f('ix_prospect_contacts_email_status'), table_name='prospect_contacts')
    op.drop_index(op.f('ix_prospect_contacts_email'), table_name='prospect_contacts')
    op.drop_index(op.f('ix_prospect_contacts_created_at'), table_name='prospect_contacts')
    op.drop_index(op.f('ix_prospect_contacts_contact_fetch_job_id'), table_name='prospect_contacts')
    op.drop_index(op.f('ix_prospect_contacts_company_id'), table_name='prospect_contacts')
    op.drop_table('prospect_contacts')
    op.drop_index('uq_contact_fetch_jobs_company_active', table_name='contact_fetch_jobs')
    op.drop_index(op.f('ix_contact_fetch_jobs_updated_at'), table_name='contact_fetch_jobs')
    op.drop_index(op.f('ix_contact_fetch_jobs_state'), table_name='contact_fetch_jobs')
    op.drop_index(op.f('ix_contact_fetch_jobs_lock_expires_at'), table_name='contact_fetch_jobs')
    op.drop_index(op.f('ix_contact_fetch_jobs_id'), table_name='contact_fetch_jobs')
    op.drop_index(op.f('ix_contact_fetch_jobs_created_at'), table_name='contact_fetch_jobs')
    op.drop_index(op.f('ix_contact_fetch_jobs_company_id'), table_name='contact_fetch_jobs')
    op.drop_table('contact_fetch_jobs')
    op.execute('DROP TYPE IF EXISTS contactfetchjobstate')
    op.drop_index(op.f('ix_title_match_rules_rule_type'), table_name='title_match_rules')
    op.drop_index(op.f('ix_title_match_rules_id'), table_name='title_match_rules')
    op.drop_index(op.f('ix_title_match_rules_created_at'), table_name='title_match_rules')
    op.drop_table('title_match_rules')
