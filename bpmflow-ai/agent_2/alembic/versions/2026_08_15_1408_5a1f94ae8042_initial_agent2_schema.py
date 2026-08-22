"""initial_agent2_schema

Revision ID: 5a1f94ae8042
Revises: 
Create Date: 2026-08-15 14:08:03.871491

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5a1f94ae8042'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. process_instances
    op.create_table(
        'process_instances',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('process_definition_id', sa.String(255), nullable=True),
        sa.Column('process_type', sa.String(100), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='CREATED'),
        sa.Column('priority', sa.String(20), nullable=False, server_default='MEDIUM'),
        sa.Column('requester_id', sa.String(255), nullable=True),
        sa.Column('requester_name', sa.String(255), nullable=True),
        sa.Column('department', sa.String(100), nullable=True),
        sa.Column('metadata_json', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 2. tasks
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('process_instance_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('process_instances.id'), nullable=False),
        sa.Column('task_definition_id', sa.String(255), nullable=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('task_type', sa.String(100), nullable=False, server_default='MANUAL'),
        sa.Column('status', sa.String(50), nullable=False, server_default='PENDING'),
        sa.Column('assigned_role', sa.String(100), nullable=True),
        sa.Column('assigned_to', sa.String(255), nullable=True),
        sa.Column('sla_hours', sa.Float(), nullable=True),
        sa.Column('priority', sa.String(20), nullable=False, server_default='MEDIUM'),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result_json', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('sequence_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 3. execution_plans
    op.create_table(
        'execution_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('process_instance_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('process_instances.id'), nullable=False),
        sa.Column('plan_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='DRAFT'),
        sa.Column('plan_json', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('approved_by', sa.String(255), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 4. execution_attempts
    op.create_table(
        'execution_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('attempt_number', sa.Integer(), server_default='1', nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='RUNNING'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result_json', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 5. tool_calls
    op.create_table(
        'tool_calls',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('execution_attempt_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('execution_attempts.id'), nullable=False),
        sa.Column('tool_name', sa.String(255), nullable=False),
        sa.Column('action', sa.String(255), nullable=False),
        sa.Column('parameters_json', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='PENDING'),
        sa.Column('result_json', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 6. execution_receipts
    op.create_table(
        'execution_receipts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('process_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('process_instances.id'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('agent_id', sa.String(100), nullable=False),
        sa.Column('tool_name', sa.String(255), nullable=False),
        sa.Column('action', sa.String(255), nullable=False),
        sa.Column('attempt_number', sa.Integer(), server_default='1', nullable=False),
        sa.Column('idempotency_key', sa.String(500), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='RUNNING'),
        sa.Column('result', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('error_type', sa.String(255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('idempotency_key', name='uq_execution_receipts_idempotency_key')
    )
    op.create_index('ix_execution_receipts_idempotency_key', 'execution_receipts', ['idempotency_key'], unique=True)

    # 7. workflow_events
    op.create_table(
        'workflow_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('process_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('process_instances.id'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=True),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('actor', sa.String(255), nullable=True),
        sa.Column('agent', sa.String(100), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('metadata_json', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('previous_state', sa.String(50), nullable=True),
        sa.Column('new_state', sa.String(50), nullable=True),
    )

    # 8. email_events
    op.create_table(
        'email_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('execution_receipt_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('execution_receipts.id'), nullable=False),
        sa.Column('recipient_email', sa.String(320), nullable=False),
        sa.Column('recipient_role', sa.String(100), nullable=False),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('template_name', sa.String(255), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='QUEUED'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 9. failures
    op.create_table(
        'failures',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('execution_receipt_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('execution_receipts.id'), nullable=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=True),
        sa.Column('failure_type', sa.String(100), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='MEDIUM'),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('resolution_status', sa.String(50), nullable=False, server_default='OPEN'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 10. retry_attempts
    op.create_table(
        'retry_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('failure_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('failures.id'), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('strategy', sa.String(100), nullable=False, server_default='EXPONENTIAL_BACKOFF'),
        sa.Column('status', sa.String(50), nullable=False, server_default='PENDING'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result_json', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 11. sla_events
    op.create_table(
        'sla_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('sla_hours', sa.Float(), nullable=False),
        sa.Column('elapsed_hours', sa.Float(), nullable=False),
        sa.Column('threshold_percent', sa.Float(), nullable=True),
        sa.Column('notified_roles', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 12. process_kpis
    op.create_table(
        'process_kpis',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('process_instance_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('process_instances.id'), nullable=True),
        sa.Column('process_type', sa.String(100), nullable=False),
        sa.Column('time_window_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('time_window_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('avg_cycle_time_hours', sa.Float(), nullable=True),
        sa.Column('avg_task_duration_hours', sa.Float(), nullable=True),
        sa.Column('completion_rate', sa.Float(), nullable=True),
        sa.Column('sla_compliance_rate', sa.Float(), nullable=True),
        sa.Column('failure_rate', sa.Float(), nullable=True),
        sa.Column('throughput', sa.Integer(), nullable=True),
        sa.Column('bottleneck_task', sa.String(255), nullable=True),
        sa.Column('kpi_data_json', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 13. optimization_recommendations
    op.create_table(
        'optimization_recommendations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('process_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('process_instances.id'), nullable=False),
        sa.Column('recommendation_type', sa.String(100), nullable=False),
        sa.Column('problem', sa.Text(), nullable=False),
        sa.Column('root_cause', sa.Text(), nullable=False),
        sa.Column('evidence', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('baseline_metric', sa.Float(), nullable=True),
        sa.Column('predicted_metric', sa.Float(), nullable=True),
        sa.Column('improvement_percent', sa.Float(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('risk', sa.String(50), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='PENDING_APPROVAL'),
        sa.Column('approved_by', sa.String(255), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 14. agent_messages
    op.create_table(
        'agent_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('message_id', sa.String(255), nullable=False),
        sa.Column('process_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('process_instances.id'), nullable=True),
        sa.Column('trace_id', sa.String(255), nullable=True),
        sa.Column('sender', sa.String(100), nullable=False),
        sa.Column('receiver', sa.String(100), nullable=False),
        sa.Column('task_type', sa.String(100), nullable=False),
        sa.Column('payload', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('evidence_refs', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='SENT'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('message_id', name='uq_agent_messages_message_id')
    )
    op.create_index('ix_agent_messages_message_id', 'agent_messages', ['message_id'], unique=True)
    op.create_index('ix_agent_messages_trace_id', 'agent_messages', ['trace_id'], unique=False)

    # 15. audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('actor', sa.String(255), nullable=False),
        sa.Column('agent', sa.String(100), nullable=True),
        sa.Column('action', sa.String(255), nullable=False),
        sa.Column('allowed', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('payload', postgresql.JSON(as_text=True), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_index('ix_agent_messages_trace_id', table_name='agent_messages')
    op.drop_index('ix_agent_messages_message_id', table_name='agent_messages')
    op.drop_table('agent_messages')
    op.drop_table('optimization_recommendations')
    op.drop_table('process_kpis')
    op.drop_table('sla_events')
    op.drop_table('retry_attempts')
    op.drop_table('failures')
    op.drop_table('email_events')
    op.drop_table('workflow_events')
    op.drop_index('ix_execution_receipts_idempotency_key', table_name='execution_receipts')
    op.drop_table('execution_receipts')
    op.drop_table('tool_calls')
    op.drop_table('execution_attempts')
    op.drop_table('execution_plans')
    op.drop_table('tasks')
    op.drop_table('process_instances')
