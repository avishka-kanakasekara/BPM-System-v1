#!/usr/bin/env python3
"""
Agent 2 — Synthetic Execution History Generator

Generates realistic multi-month procurement process history (600–1000 process instances)
for purchase-request-to-completion workflow.

Seeds:
- process_instances & tasks (5 stages per process)
- execution_plans, execution_attempts, tool_calls, execution_receipts
- workflow_events (including REWORK events)
- failures & retry_attempts
- sla_events (WARNING & BREACHED)
- email_events (6 notification types)
- process_kpis (aggregated analytics snapshots)

Target Distributions:
- Request validation: ~12 min mean (automated)
- Manager approval: ~18.4h mean (human bottleneck)
- Finance approval: ~11.2h mean (human approval)
- PO creation: ~8 min mean (automated)
- Invoice matching: ~22 min mean (automated)
- Approval SLA breach rate: 15–20% (> 24h)
- Rework rate: ~25% (55% missing cost centre, 35% missing quotation, 10% incorrect supplier)
- Tool call failure rate: ~5–8% across 9 failure types with retry recovery
- Email delivery rate: >97% success

Usage:
    python data/synthetic_cases/generate_history.py [--count 750] [--reset]
"""

import argparse
import asyncio
import json
import math
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure agent_2 package root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from app.database.models import (
    AgentMessage,
    AuditLog,
    Base,
    EmailEvent,
    ExecutionAttempt,
    ExecutionPlan,
    ExecutionReceipt,
    Failure,
    OptimizationRecommendation,
    ProcessInstance,
    ProcessKPI,
    RetryAttempt,
    SLAEvent,
    Task,
    ToolCall,
    WorkflowEvent,
)

# ---------------------------------------------------------------------------
# Organization Directory (Agent 3 Mock)
# ---------------------------------------------------------------------------

ORG_DIR_PATH = os.path.join(os.path.dirname(__file__), "org_directory.json")

def load_org_directory():
    if os.path.exists(ORG_DIR_PATH):
        with open(ORG_DIR_PATH, "r") as f:
            return json.load(f).get("users", [])
    return []

USERS = load_org_directory()
REQUESTERS = [u for u in USERS if u.get("role") == "requester"] or [{"name": "Alice Johnson", "email": "alice@acme.com"}]
MANAGERS = [u for u in USERS if u.get("role") == "manager"] or [{"name": "Frank Miller", "email": "frank@acme.com"}]
FINANCE = [u for u in USERS if u.get("role") == "finance_officer"] or [{"name": "Henry Taylor", "email": "henry@acme.com"}]
PROCUREMENT = [u for u in USERS if u.get("role") == "procurement_officer"] or [{"name": "Jack Thomas", "email": "jack@acme.com"}]
EMPLOYEES = [u for u in USERS if u.get("role") == "assigned_employee"] or [{"name": "David Brown", "email": "david@acme.com"}]

# ---------------------------------------------------------------------------
# Lognormal Duration Generator
# ---------------------------------------------------------------------------

def sample_lognormal_minutes(target_mean_minutes: float, sigma: float = 0.35) -> float:
    """Sample duration in minutes from lognormal distribution with target mean."""
    mu = math.log(target_mean_minutes) - (sigma ** 2) / 2.0
    val = random.lognormvariate(mu, sigma)
    return max(1.0, val)

def sample_lognormal_hours(target_mean_hours: float, sigma: float = 0.4) -> float:
    """Sample duration in hours from lognormal distribution with target mean."""
    mu = math.log(target_mean_hours) - (sigma ** 2) / 2.0
    val = random.lognormvariate(mu, sigma)
    return max(0.1, val)

# ---------------------------------------------------------------------------
# DB Engine Setup
# ---------------------------------------------------------------------------

def get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if os.getenv("USE_SQLITE", "").lower() == "true" or not url:
        return "sqlite+aiosqlite:///bpmflow_agent2.db"
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url

# ---------------------------------------------------------------------------
# Main Seeding Logic
# ---------------------------------------------------------------------------

async def seed_synthetic_history(count: int = 750, reset: bool = False):
    db_url = get_db_url()
    connect_args = {"statement_cache_size": 0, "ssl": "require"} if "postgresql" in db_url else {}
    engine = create_async_engine(
        db_url,
        echo=False,
        connect_args=connect_args,
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        if reset:
            print("Resetting Agent 2 database tables...")
            tables_to_truncate = [
                "retry_attempts",
                "failures",
                "email_events",
                "workflow_events",
                "execution_receipts",
                "tool_calls",
                "execution_attempts",
                "execution_plans",
                "sla_events",
                "process_kpis",
                "optimization_recommendations",
                "agent_messages",
                "audit_logs",
                "tasks",
                "process_instances",
            ]
            for t in tables_to_truncate:
                stmt_del = f"DELETE FROM {t};" if "sqlite" in db_url else f"TRUNCATE TABLE {t} CASCADE;"
                await session.execute(text(stmt_del))
            await session.commit()
            print("Tables truncated successfully.")

        print(f"Generating synthetic history for {count} procurement cases...")

        # Base time window: past 90 days
        now = datetime.now(timezone.utc)
        start_history = now - timedelta(days=90)

        # Track statistics
        stats = {
            "process_instances": 0,
            "tasks": 0,
            "execution_plans": 0,
            "execution_attempts": 0,
            "tool_calls": 0,
            "execution_receipts": 0,
            "workflow_events": 0,
            "email_events": 0,
            "failures": 0,
            "retry_attempts": 0,
            "sla_events": 0,
            "process_kpis": 0,
            "durations": {
                "request_validation": [],
                "manager_approval": [],
                "finance_approval": [],
                "po_creation": [],
                "invoice_matching": [],
            },
            "sla_breaches": 0,
            "approval_tasks_count": 0,
            "rework_count": 0,
            "rework_reasons": {
                "missing cost centre": 0,
                "missing quotation": 0,
                "incorrect supplier": 0,
            },
        }

        failure_types_distribution = [
            ("TEMPORARY", 0.35),
            ("TIMEOUT", 0.35),
            ("DUPLICATE", 0.10),
            ("RATE_LIMIT", 0.10),
            ("AUTHORIZATION", 0.05),
            ("PERMANENT", 0.05),
        ]

        def random_failure_type():
            r = random.random()
            cum = 0.0
            for ft, prob in failure_types_distribution:
                cum += prob
                if r <= cum:
                    return ft
            return "TEMPORARY"

        # Generate cases
        for i in range(count):
            # Spread process creation over past 90 days
            offset_seconds = random.uniform(0, 85 * 86400)
            proc_created_at = start_history + timedelta(seconds=offset_seconds)

            requester = random.choice(REQUESTERS)
            manager = random.choice(MANAGERS)
            finance_officer = random.choice(FINANCE)
            proc_officer = random.choice(PROCUREMENT)

            amount = round(random.uniform(250.0, 45000.0), 2)
            dept = requester.get("department", "Engineering")

            proc_instance = ProcessInstance(
                id=uuid.uuid4(),
                process_definition_id="procdef-procurement-v1",
                process_type="procurement",
                title=f"Purchase Request: Hardware & Supplies #{1000 + i}",
                description=f"Automated procurement request for {dept} dept ($ {amount})",
                status="COMPLETED",
                priority="HIGH" if amount > 10000 else "MEDIUM",
                requester_id=requester.get("id"),
                requester_name=requester.get("name"),
                department=dept,
                metadata_json={"amount": amount, "currency": "USD"},
                created_at=proc_created_at,
                updated_at=proc_created_at + timedelta(hours=30),
            )
            session.add(proc_instance)
            stats["process_instances"] += 1

            current_time = proc_created_at

            # Workflow Event: CREATED
            we_create = WorkflowEvent(
                id=uuid.uuid4(),
                process_id=proc_instance.id,
                event_type="PROCESS_STARTED",
                actor=requester.get("email"),
                agent="agent_1",
                timestamp=current_time,
                previous_state=None,
                new_state="CREATED",
                metadata_json={"amount": amount},
            )
            session.add(we_create)
            stats["workflow_events"] += 1

            # Execution Plan
            plan = ExecutionPlan(
                id=uuid.uuid4(),
                process_instance_id=proc_instance.id,
                plan_version=1,
                status="APPROVED",
                plan_json={
                    "steps": ["request_validation", "manager_approval", "finance_approval", "po_creation", "invoice_matching"]
                },
                reasoning="Standard 5-stage procurement plan",
                created_at=current_time,
                updated_at=current_time,
            )
            session.add(plan)
            stats["execution_plans"] += 1

            # Check if this case experiences Rework (~25% probability)
            has_rework = random.random() < 0.25
            rework_reason = None
            if has_rework:
                stats["rework_count"] += 1
                r_val = random.random()
                if r_val < 0.55:
                    rework_reason = "missing cost centre"
                elif r_val < 0.90:
                    rework_reason = "missing quotation"
                else:
                    rework_reason = "incorrect supplier"
                stats["rework_reasons"][rework_reason] += 1

            # ── STAGE 1: Request Validation (Automated) ───────────────────
            val_duration_min = sample_lognormal_minutes(12.0, sigma=0.35)
            stats["durations"]["request_validation"].append(val_duration_min)

            task_val = Task(
                id=uuid.uuid4(),
                process_instance_id=proc_instance.id,
                title="Request Validation",
                task_type="AUTOMATED",
                status="COMPLETED",
                assigned_role="system",
                sla_hours=1.0,
                priority="MEDIUM",
                sequence_order=1,
                started_at=current_time,
                completed_at=current_time + timedelta(minutes=val_duration_min),
                created_at=current_time,
                updated_at=current_time + timedelta(minutes=val_duration_min),
            )
            session.add(task_val)
            stats["tasks"] += 1
            current_time = task_val.completed_at

            # Tool call & receipt for Validation
            receipt_val = ExecutionReceipt(
                id=uuid.uuid4(),
                process_id=proc_instance.id,
                task_id=task_val.id,
                agent_id="agent_2",
                tool_name="validate_procurement_request",
                action="VALIDATE",
                attempt_number=1,
                idempotency_key=f"{proc_instance.id}-{task_val.id}-VALIDATE",
                started_at=task_val.started_at,
                completed_at=task_val.completed_at,
                status="SUCCESS",
                result={"valid": True, "amount": amount},
                latency_ms=int(val_duration_min * 60 * 1000),
                created_at=task_val.started_at,
                updated_at=task_val.completed_at,
            )
            session.add(receipt_val)
            stats["execution_receipts"] += 1

            # ── STAGE 2: Manager Approval (Human Bottleneck) ─────────────
            # Target mean ~ 18.4 hours. ~18% breach SLA of 24h
            is_mgr_breached = random.random() < 0.18
            if is_mgr_breached:
                mgr_duration_hours = sample_lognormal_hours(31.0, sigma=0.3)  # force breach (>24h)
            else:
                mgr_duration_hours = sample_lognormal_hours(15.6, sigma=0.35) # under SLA

            stats["durations"]["manager_approval"].append(mgr_duration_hours)
            stats["approval_tasks_count"] += 1

            task_mgr = Task(
                id=uuid.uuid4(),
                process_instance_id=proc_instance.id,
                title="Manager Approval",
                task_type="HUMAN_APPROVAL",
                status="COMPLETED",
                assigned_role="manager",
                assigned_to=manager.get("email"),
                sla_hours=24.0,
                priority="HIGH" if amount > 10000 else "MEDIUM",
                sequence_order=2,
                started_at=current_time,
                completed_at=current_time + timedelta(hours=mgr_duration_hours),
                created_at=current_time,
                updated_at=current_time + timedelta(hours=mgr_duration_hours),
            )
            session.add(task_mgr)
            stats["tasks"] += 1

            if mgr_duration_hours > 24.0:
                stats["sla_breaches"] += 1
                sla_ev = SLAEvent(
                    id=uuid.uuid4(),
                    task_id=task_mgr.id,
                    event_type="BREACHED",
                    sla_hours=24.0,
                    elapsed_hours=round(mgr_duration_hours, 2),
                    threshold_percent=100.0,
                    notified_roles={"manager": manager.get("email")},
                    message=f"Task Manager Approval exceeded SLA of 24h (elapsed: {mgr_duration_hours:.1f}h)",
                    created_at=current_time + timedelta(hours=24.0),
                )
                session.add(sla_ev)
                stats["sla_events"] += 1

            # Task assignment email to manager
            email_mgr = EmailEvent(
                id=uuid.uuid4(),
                execution_receipt_id=receipt_val.id,
                recipient_email=manager.get("email"),
                recipient_role="manager",
                subject=f"Approval Required: Purchase Request #{1000 + i}",
                template_name="approval_request.html",
                status="SENT",
                sent_at=current_time,
                created_at=current_time,
            )
            session.add(email_mgr)
            stats["email_events"] += 1

            current_time = task_mgr.completed_at

            # If Rework happened at Manager stage
            if has_rework:
                rework_ev = WorkflowEvent(
                    id=uuid.uuid4(),
                    process_id=proc_instance.id,
                    task_id=task_mgr.id,
                    event_type="REWORK",
                    actor=manager.get("email"),
                    agent="agent_2",
                    timestamp=current_time - timedelta(hours=1.0),
                    previous_state="PENDING_APPROVAL",
                    new_state="REWORK_REQUESTED",
                    metadata_json={"reason": rework_reason},
                )
                session.add(rework_ev)
                stats["workflow_events"] += 1

                failure_row = Failure(
                    id=uuid.uuid4(),
                    task_id=task_mgr.id,
                    failure_type="DATA",
                    severity="MEDIUM",
                    description=f"Rework requested by manager: {rework_reason}",
                    root_cause=rework_reason,
                    resolution_status="RESOLVED",
                    resolved_at=current_time,
                    created_at=current_time - timedelta(hours=1.0),
                )
                session.add(failure_row)
                stats["failures"] += 1

            # ── STAGE 3: Finance Approval (Human Approval) ────────────────
            # Target mean ~ 11.2 hours. ~15% breach SLA of 24h
            is_fin_breached = random.random() < 0.15
            if is_fin_breached:
                fin_duration_hours = sample_lognormal_hours(29.0, sigma=0.3)
            else:
                fin_duration_hours = sample_lognormal_hours(9.4, sigma=0.35)

            stats["durations"]["finance_approval"].append(fin_duration_hours)
            stats["approval_tasks_count"] += 1

            task_fin = Task(
                id=uuid.uuid4(),
                process_instance_id=proc_instance.id,
                title="Finance Approval",
                task_type="HUMAN_APPROVAL",
                status="COMPLETED",
                assigned_role="finance_officer",
                assigned_to=finance_officer.get("email"),
                sla_hours=24.0,
                priority="MEDIUM",
                sequence_order=3,
                started_at=current_time,
                completed_at=current_time + timedelta(hours=fin_duration_hours),
                created_at=current_time,
                updated_at=current_time + timedelta(hours=fin_duration_hours),
            )
            session.add(task_fin)
            stats["tasks"] += 1

            if fin_duration_hours > 24.0:
                stats["sla_breaches"] += 1
                sla_ev_fin = SLAEvent(
                    id=uuid.uuid4(),
                    task_id=task_fin.id,
                    event_type="BREACHED",
                    sla_hours=24.0,
                    elapsed_hours=round(fin_duration_hours, 2),
                    threshold_percent=100.0,
                    notified_roles={"finance_officer": finance_officer.get("email")},
                    message=f"Finance Approval exceeded SLA of 24h (elapsed: {fin_duration_hours:.1f}h)",
                    created_at=current_time + timedelta(hours=24.0),
                )
                session.add(sla_ev_fin)
                stats["sla_events"] += 1

            current_time = task_fin.completed_at

            # ── STAGE 4: PO Creation (Automated) ──────────────────────────
            po_duration_min = sample_lognormal_minutes(8.0, sigma=0.3)
            stats["durations"]["po_creation"].append(po_duration_min)

            task_po = Task(
                id=uuid.uuid4(),
                process_instance_id=proc_instance.id,
                title="PO Creation",
                task_type="AUTOMATED",
                status="COMPLETED",
                assigned_role="system",
                sla_hours=2.0,
                priority="MEDIUM",
                sequence_order=4,
                started_at=current_time,
                completed_at=current_time + timedelta(minutes=po_duration_min),
                created_at=current_time,
                updated_at=current_time + timedelta(minutes=po_duration_min),
            )
            session.add(task_po)
            stats["tasks"] += 1

            # Check for simulated tool failure (~6% chance)
            has_tool_failure = random.random() < 0.06
            attempt_num = 1
            if has_tool_failure:
                ftype = random_failure_type()

                exec_att_1 = ExecutionAttempt(
                    id=uuid.uuid4(),
                    task_id=task_po.id,
                    attempt_number=1,
                    status="FAILED",
                    started_at=current_time,
                    completed_at=current_time + timedelta(seconds=15),
                    error_message=f"Tool call failed with {ftype}",
                )
                session.add(exec_att_1)
                stats["execution_attempts"] += 1

                tc_fail = ToolCall(
                    id=uuid.uuid4(),
                    execution_attempt_id=exec_att_1.id,
                    tool_name="create_po_draft",
                    action="CREATE_PO",
                    status="FAILED",
                    error_message=f"ERP connector exception: {ftype}",
                    started_at=current_time,
                    completed_at=current_time + timedelta(seconds=15),
                    latency_ms=15000,
                )
                session.add(tc_fail)
                stats["tool_calls"] += 1

                receipt_fail = ExecutionReceipt(
                    id=uuid.uuid4(),
                    process_id=proc_instance.id,
                    task_id=task_po.id,
                    agent_id="agent_2",
                    tool_name="create_po_draft",
                    action="CREATE_PO",
                    attempt_number=1,
                    idempotency_key=f"{proc_instance.id}-{task_po.id}-CREATE_PO-att1",
                    started_at=current_time,
                    completed_at=current_time + timedelta(seconds=15),
                    status="FAILED",
                    error_type=ftype,
                    error_message=f"ERP timeout error: {ftype}",
                    latency_ms=15000,
                )
                session.add(receipt_fail)
                stats["execution_receipts"] += 1

                fail_rec = Failure(
                    id=uuid.uuid4(),
                    execution_receipt_id=receipt_fail.id,
                    task_id=task_po.id,
                    failure_type=ftype,
                    severity="MEDIUM",
                    description=f"ERP PO creation tool error: {ftype}",
                    root_cause=ftype,
                    resolution_status="RESOLVED" if ftype in ["TEMPORARY", "TIMEOUT", "RATE_LIMIT"] else "OPEN",
                    resolved_at=task_po.completed_at,
                )
                session.add(fail_rec)
                stats["failures"] += 1

                if ftype in ["TEMPORARY", "TIMEOUT", "RATE_LIMIT", "DUPLICATE"]:
                    retry_rec = RetryAttempt(
                        id=uuid.uuid4(),
                        failure_id=fail_rec.id,
                        attempt_number=2,
                        strategy="EXPONENTIAL_BACKOFF",
                        status="COMPLETED",
                        started_at=current_time + timedelta(seconds=30),
                        completed_at=task_po.completed_at,
                        result_json={"status": "RECOVERED"},
                    )
                    session.add(retry_rec)
                    stats["retry_attempts"] += 1

                attempt_num = 2

            exec_att_succ = ExecutionAttempt(
                id=uuid.uuid4(),
                task_id=task_po.id,
                attempt_number=attempt_num,
                status="COMPLETED",
                started_at=current_time,
                completed_at=task_po.completed_at,
                result_json={"po_number": f"PO-2026-{10000 + i}"},
            )
            session.add(exec_att_succ)
            stats["execution_attempts"] += 1

            tc_succ = ToolCall(
                id=uuid.uuid4(),
                execution_attempt_id=exec_att_succ.id,
                tool_name="create_po_draft",
                action="CREATE_PO",
                status="SUCCESS",
                result_json={"po_number": f"PO-2026-{10000 + i}"},
                started_at=current_time,
                completed_at=task_po.completed_at,
                latency_ms=int(po_duration_min * 60 * 1000),
            )
            session.add(tc_succ)
            stats["tool_calls"] += 1

            receipt_po = ExecutionReceipt(
                id=uuid.uuid4(),
                process_id=proc_instance.id,
                task_id=task_po.id,
                agent_id="agent_2",
                tool_name="create_po_draft",
                action="CREATE_PO",
                attempt_number=attempt_num,
                idempotency_key=f"{proc_instance.id}-{task_po.id}-CREATE_PO",
                started_at=current_time,
                completed_at=task_po.completed_at,
                status="SUCCESS",
                result={"po_number": f"PO-2026-{10000 + i}"},
                latency_ms=int(po_duration_min * 60 * 1000),
            )
            session.add(receipt_po)
            stats["execution_receipts"] += 1

            current_time = task_po.completed_at

            # ── STAGE 5: Invoice Matching (Automated) ─────────────────────
            inv_duration_min = sample_lognormal_minutes(22.0, sigma=0.35)
            stats["durations"]["invoice_matching"].append(inv_duration_min)

            task_inv = Task(
                id=uuid.uuid4(),
                process_instance_id=proc_instance.id,
                title="Invoice Matching",
                task_type="AUTOMATED",
                status="COMPLETED",
                assigned_role="system",
                sla_hours=4.0,
                priority="LOW",
                sequence_order=5,
                started_at=current_time,
                completed_at=current_time + timedelta(minutes=inv_duration_min),
                created_at=current_time,
                updated_at=current_time + timedelta(minutes=inv_duration_min),
            )
            session.add(task_inv)
            stats["tasks"] += 1

            receipt_inv = ExecutionReceipt(
                id=uuid.uuid4(),
                process_id=proc_instance.id,
                task_id=task_inv.id,
                agent_id="agent_2",
                tool_name="match_invoice",
                action="MATCH_INVOICE",
                attempt_number=1,
                idempotency_key=f"{proc_instance.id}-{task_inv.id}-MATCH_INVOICE",
                started_at=current_time,
                completed_at=task_inv.completed_at,
                status="SUCCESS",
                result={"matched": True, "invoice_id": f"INV-900{i}"},
                latency_ms=int(inv_duration_min * 60 * 1000),
            )
            session.add(receipt_inv)
            stats["execution_receipts"] += 1

            # Completion Email
            email_comp = EmailEvent(
                id=uuid.uuid4(),
                execution_receipt_id=receipt_inv.id,
                recipient_email=requester.get("email"),
                recipient_role="requester",
                subject=f"Procurement Order Completed: #{1000 + i}",
                template_name="order_completion.html",
                status="SENT" if random.random() > 0.02 else "FAILED",
                sent_at=task_inv.completed_at,
            )
            session.add(email_comp)
            stats["email_events"] += 1

            # Commit batch every 50 instances to keep memory lightweight
            if (i + 1) % 50 == 0:
                await session.commit()

        # Seed Process KPIs snapshot
        kpi_snapshot = ProcessKPI(
            id=uuid.uuid4(),
            process_type="procurement",
            time_window_start=start_history,
            time_window_end=now,
            avg_cycle_time_hours=sum(
                [sum(v) / len(v) if k in ["manager_approval", "finance_approval"] else (sum(v) / len(v)) / 60.0 for k, v in stats["durations"].items()]
            ),
            avg_task_duration_hours=sum(stats["durations"]["manager_approval"]) / len(stats["durations"]["manager_approval"]),
            completion_rate=1.0,
            sla_compliance_rate=1.0 - (stats["sla_breaches"] / max(1, stats["approval_tasks_count"])),
            failure_rate=stats["failures"] / max(1, stats["tasks"]),
            throughput=count,
            bottleneck_task="Manager Approval",
            kpi_data_json={"total_cases": count, "rework_rate": stats["rework_count"] / float(count)},
        )
        session.add(kpi_snapshot)
        stats["process_kpis"] += 1

        await session.commit()

    await engine.dispose()

    # ---------------------------------------------------------------------------
    # Summary Output
    # ---------------------------------------------------------------------------

    mean_val = sum(stats["durations"]["request_validation"]) / len(stats["durations"]["request_validation"])
    mean_mgr = sum(stats["durations"]["manager_approval"]) / len(stats["durations"]["manager_approval"])
    mean_fin = sum(stats["durations"]["finance_approval"]) / len(stats["durations"]["finance_approval"])
    mean_po = sum(stats["durations"]["po_creation"]) / len(stats["durations"]["po_creation"])
    mean_inv = sum(stats["durations"]["invoice_matching"]) / len(stats["durations"]["invoice_matching"])

    breach_rate = (stats["sla_breaches"] / max(1, stats["approval_tasks_count"])) * 100.0
    rework_rate = (stats["rework_count"] / float(count)) * 100.0

    print("\n" + "=" * 70)
    print("      SYNTHETIC HISTORY SEEDING SUMMARY      ")
    print("=" * 70)
    print(f"  process_instances:       {stats['process_instances']}")
    print(f"  tasks:                   {stats['tasks']}")
    print(f"  execution_plans:         {stats['execution_plans']}")
    print(f"  execution_attempts:      {stats['execution_attempts']}")
    print(f"  tool_calls:              {stats['tool_calls']}")
    print(f"  execution_receipts:      {stats['execution_receipts']}")
    print(f"  workflow_events:         {stats['workflow_events']}")
    print(f"  email_events:            {stats['email_events']}")
    print(f"  failures:                {stats['failures']}")
    print(f"  retry_attempts:          {stats['retry_attempts']}")
    print(f"  sla_events:              {stats['sla_events']}")
    print(f"  process_kpis:            {stats['process_kpis']}")
    print("-" * 70)
    print("  COMPUTED STAGE MEAN DURATIONS:")
    print(f"    • Request validation:   {mean_val:.2f} min (Target: ~12 min)")
    print(f"    • Manager approval:     {mean_mgr:.2f} hours (Target: ~18.4 hours - BOTTLENECK)")
    print(f"    • Finance approval:     {mean_fin:.2f} hours (Target: ~11.2 hours)")
    print(f"    • PO creation:          {mean_po:.2f} min (Target: ~8 min)")
    print(f"    • Invoice matching:     {mean_inv:.2f} min (Target: ~22 min)")
    print("-" * 70)
    print(f"  APPROVAL SLA BREACH RATE: {breach_rate:.2f}% (Target: 15–20%)")
    print(f"  REWORK RATE:              {rework_rate:.2f}% (Target: ~25%)")
    print("  REWORK REASONS BREAKDOWN:")
    for reason, count_val in stats["rework_reasons"].items():
        pct = (count_val / max(1, stats["rework_count"])) * 100.0
        print(f"    • {reason:<22}: {count_val:3d} ({pct:.1f}%)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic execution history for Agent 2.")
    parser.add_argument("--count", type=int, default=750, help="Number of process instances to generate (default 750)")
    parser.add_argument("--reset", action="store_true", help="Truncate database tables before seeding")
    args = parser.parse_args()

    asyncio.run(seed_synthetic_history(count=args.count, reset=args.reset))
