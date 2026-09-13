"""End-to-end smoke test against a running BPMFlow API server (G1–G8).

Drives the procurement golden path over HTTP, prints a pass/fail table with
timings and entity IDs, and exits non-zero on any failure.

Usage (from bpmflow-ai/backend):
  uvicorn app.main:app --host 127.0.0.1 --port 8000
  python -m app.scripts.e2e_smoke

Cold start (migrate + seed + start server + smoke + stop):
  python -m app.scripts.e2e_smoke --cold-start

Environment:
  E2E_BASE_URL          API root (default http://127.0.0.1:8000)
  E2E_BEARER_TOKEN      Pre-obtained JWT (optional)
  E2E_APPROVER_TOKEN    JWT with approver/admin role (optional)
  E2E_EMAIL / E2E_PASSWORD / E2E_APPROVER_EMAIL / E2E_APPROVER_PASSWORD
  SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_JWT_SECRET (auth fallback)
  DEMO_TENANT_ID        Demo tenant for Agent 3 (default 000…001)
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from jose import jwt

BPMFLOW_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DIR = BPMFLOW_ROOT / "sample-documents"
DEFAULT_BASE = "http://127.0.0.1:8000"
DEMO_TENANT = "00000000-0000-0000-0000-000000000001"
FORBIDDEN_RESPONSE_MARKERS = (
    "empty scaffold",
    "not implemented",
    "TODO",
    "FIXME",
    "sample data only",
)


@dataclass
class GateResult:
    gate: str
    check: str
    passed: bool
    elapsed_ms: float
    detail: str = ""
    ids: str = ""


@dataclass
class SmokeContext:
    base_url: str
    client: httpx.Client
    requester_token: str
    approver_token: str | None = None
    process_id: str | None = None
    approval_id: str | None = None
    receipt_id: str | None = None
    results: list[GateResult] = field(default_factory=list)

    def record(
        self,
        gate: str,
        check: str,
        passed: bool,
        started: float,
        *,
        detail: str = "",
        ids: str = "",
    ) -> None:
        elapsed = (time.perf_counter() - started) * 1000
        self.results.append(
            GateResult(
                gate=gate,
                check=check,
                passed=passed,
                elapsed_ms=elapsed,
                detail=detail,
                ids=ids,
            )
        )

    def auth_headers(self, *, approver: bool = False) -> dict[str, str]:
        token = self.approver_token if approver and self.approver_token else self.requester_token
        return {"Authorization": f"Bearer {token}"}


def _load_settings() -> Any:
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.config import settings

    return settings


def _mint_hs256(*, sub: str, secret: str, tenant_id: str | None = None) -> str:
    now = datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "role": "authenticated",
    }
    if tenant_id:
        payload["app_metadata"] = {"tenant_id": tenant_id}
    return jwt.encode(payload, secret, algorithm="HS256")


def _password_grant(email: str, password: str, settings: Any) -> str:
    base = (settings.SUPABASE_URL or "").rstrip("/")
    anon = (settings.SUPABASE_ANON_KEY or "").strip()
    if not base or not anon:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY required for password grant")
    response = httpx.post(
        f"{base}/auth/v1/token?grant_type=password",
        headers={"apikey": anon, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=30.0,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("Password grant did not return access_token")
    return token


def _register_dev_user(
    client: httpx.Client,
    *,
    email: str,
    password: str,
    role: str,
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "E2E Smoke", "role": role},
    )
    if response.status_code not in {201, 409}:
        raise RuntimeError(f"register failed ({response.status_code}): {response.text[:200]}")


def _resolve_tokens(client: httpx.Client, settings: Any) -> tuple[str, str | None]:
    bearer = (os.environ.get("E2E_BEARER_TOKEN") or "").strip()
    approver = (os.environ.get("E2E_APPROVER_TOKEN") or "").strip() or None
    if bearer:
        return bearer, approver

    secret = (settings.SUPABASE_JWT_SECRET or os.environ.get("SUPABASE_JWT_SECRET") or "").strip()
    user_id = (os.environ.get("E2E_USER_ID") or "").strip()
    tenant = (settings.DEMO_TENANT_ID or DEMO_TENANT).strip()
    if secret and user_id:
        return _mint_hs256(sub=user_id, secret=secret, tenant_id=tenant), approver

    suffix = uuid.uuid4().hex[:8]
    req_email = os.environ.get("E2E_EMAIL") or f"e2e-requester-{suffix}@example.com"
    req_password = os.environ.get("E2E_PASSWORD") or "E2eSmokePass1!"
    appr_email = os.environ.get("E2E_APPROVER_EMAIL") or f"e2e-approver-{suffix}@example.com"
    appr_password = os.environ.get("E2E_APPROVER_PASSWORD") or "E2eSmokePass1!"

    _register_dev_user(client, email=req_email, password=req_password, role="requester")
    _register_dev_user(client, email=appr_email, password=appr_password, role="approver")
    requester = _password_grant(req_email, req_password, settings)
    approver_token = _password_grant(appr_email, appr_password, settings)
    return requester, approver_token


def _wait_for_health(base_url: str, timeout_seconds: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "unknown"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{base_url}/health/live", timeout=5.0)
            if response.status_code == 200:
                return
            last_error = f"status {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(1.0)
    raise RuntimeError(f"Server not healthy at {base_url}/health/live: {last_error}")


def _start_server(base_url: str) -> subprocess.Popen[Any]:
    host_port = base_url.rstrip("/").replace("http://", "").replace("https://", "")
    if ":" in host_port:
        host, port = host_port.split(":", 1)
    else:
        host, port = host_port, "8000"
    env = os.environ.copy()
    env.setdefault("GEMINI_OFFLINE", "true")
    env.setdefault("MOCK_LLM", "true")
    env.setdefault("ENV", "development")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host or "127.0.0.1",
        "--port",
        port,
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _wait_for_health(base_url)
    return proc


def _cold_start(base_url: str) -> subprocess.Popen[Any] | None:
    backend = Path(__file__).resolve().parents[2]
    for script in ("apply_pending_migrations", "seed_demo_tenant"):
        print(f"[cold-start] running app.scripts.{script} …")
        result = subprocess.run(
            [sys.executable, "-m", f"app.scripts.{script}"],
            cwd=str(backend),
            env=os.environ.copy(),
        )
        if script == "apply_pending_migrations" and result.returncode != 0:
            print("[cold-start] migrations unavailable — continuing with REST persistence")
    print("[cold-start] starting uvicorn …")
    return _start_server(base_url)


def gate_g1_health(ctx: SmokeContext) -> None:
    started = time.perf_counter()
    try:
        live = ctx.client.get("/health/live")
        deps = ctx.client.get("/health/deps")
        live_ok = live.status_code == 200 and live.json().get("status") == "alive"
        deps_body = deps.json() if deps.status_code in {200, 503} else {}
        probes = deps_body.get("probes") or deps_body.get("dependencies") or {}
        persistence_ok = False
        if isinstance(probes, dict):
            for name, probe in probes.items():
                status = str((probe or {}).get("status") or "")
                if name in {"postgres", "supabase_rest"} and status == "ok":
                    persistence_ok = True
        ready = deps_body.get("ready")
        if ready is True:
            persistence_ok = True
        passed = live_ok and persistence_ok
        detail = f"live={live.status_code} deps={deps.status_code} ready={ready}"
    except Exception as exc:
        passed = False
        detail = str(exc)
    ctx.record("G1", "Boot / health probes", passed, started, detail=detail)


def gate_g2_discovery(ctx: SmokeContext) -> None:
    started = time.perf_counter()
    try:
        created = ctx.client.post(
            "/api/v1/processes",
            headers=ctx.auth_headers(),
            json={"name": f"E2E Smoke {uuid.uuid4().hex[:6]}", "process_type": "procurement"},
        )
        created.raise_for_status()
        ctx.process_id = created.json()["id"]

        csv_path = SAMPLE_DIR / "procurement_event_log.csv"
        docx_path = SAMPLE_DIR / "procurement_purchase_request.docx"
        files = []
        if csv_path.is_file():
            files.append(("files", (csv_path.name, csv_path.read_bytes(), "text/csv")))
        if docx_path.is_file():
            files.append(
                (
                    "files",
                    (
                        docx_path.name,
                        docx_path.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                )
            )
        if not files:
            raise FileNotFoundError(f"No sample documents under {SAMPLE_DIR}")

        discover = ctx.client.post(
            "/api/v1/agent1/discover",
            headers=ctx.auth_headers(),
            data={"process_id": ctx.process_id},
            files=files,
            timeout=120.0,
        )
        discover.raise_for_status()
        detail_row = ctx.client.get(
            f"/api/v1/agent1/processes/{ctx.process_id}",
            headers=ctx.auth_headers(),
        )
        detail_row.raise_for_status()
        body = detail_row.json()
        activities = (body.get("process_json") or {}).get("activities") or []
        analytics = (body.get("process_json") or {}).get("analytics") or {}
        risk_facts = analytics.get("risk_facts") if isinstance(analytics, dict) else {}
        passed = len(activities) >= 1 or bool(risk_facts)
        detail = f"activities={len(activities)} risk_facts={bool(risk_facts)}"
        ids = f"process={ctx.process_id}"
    except Exception as exc:
        passed = False
        detail = str(exc)
        ids = f"process={ctx.process_id or '—'}"
    ctx.record("G2", "Agent 1 discovery upload", passed, started, detail=detail, ids=ids)


def gate_g3_resource_planning(ctx: SmokeContext) -> None:
    started = time.perf_counter()
    if not ctx.process_id:
        ctx.record("G3", "Agent 3 allocation", False, started, detail="no process_id")
        return
    try:
        tenant = (os.environ.get("DEMO_TENANT_ID") or DEMO_TENANT).strip()
        advance = ctx.client.post(
            f"/api/v1/processes/{ctx.process_id}/advance",
            headers=ctx.auth_headers(),
            json={
                "idempotency_key": f"e2e-g3-{uuid.uuid4().hex[:8]}",
                "max_steps": 3,
                "resource_planning": {
                    "task_id": str(uuid.uuid4()),
                    "tenant_id": tenant,
                    "human_requirements": {"skills": ["python"]},
                    "budget_requirements": {"amount": "5000", "currency": "USD"},
                },
            },
            timeout=120.0,
        )
        advance.raise_for_status()
        adv = advance.json().get("advancement") or {}
        actions = adv.get("autonomous_actions") or []
        resource_ok = any(a.get("action") == "RESOURCE_PLANNING" and a.get("success") for a in actions)
        passed = resource_ok or adv.get("steps_taken", 0) >= 1
        detail = f"steps={adv.get('steps_taken')} resource_ok={resource_ok}"
        ids = f"process={ctx.process_id}"
    except Exception as exc:
        passed = False
        detail = str(exc)
        ids = f"process={ctx.process_id}"
    ctx.record("G3", "Agent 3 resource planning", passed, started, detail=detail, ids=ids)


def gate_g4_execution(ctx: SmokeContext) -> None:
    started = time.perf_counter()
    if not ctx.process_id:
        ctx.record("G4", "Agent 2 execution", False, started, detail="no process_id")
        return
    try:
        advance = ctx.client.post(
            f"/api/v1/processes/{ctx.process_id}/advance",
            headers=ctx.auth_headers(),
            json={"idempotency_key": f"e2e-g4-{uuid.uuid4().hex[:8]}", "max_steps": 8},
            timeout=180.0,
        )
        advance.raise_for_status()
        body = advance.json()
        stage = body.get("process", {}).get("current_stage")
        adv = body.get("advancement") or {}

        if stage == "AWAITING_HUMAN_APPROVAL" and ctx.approver_token:
            approvals = ctx.client.get("/api/v1/approvals", headers=ctx.auth_headers(approver=True))
            approvals.raise_for_status()
            pending = [
                row
                for row in approvals.json()
                if row.get("status") == "PENDING" and str(row.get("process_id")) == ctx.process_id
            ]
            if pending:
                ctx.approval_id = pending[0]["id"]
                decision = ctx.client.post(
                    f"/api/v1/approvals/{ctx.approval_id}/approve",
                    headers=ctx.auth_headers(approver=True),
                    json={"comments": "E2E smoke approval"},
                    timeout=120.0,
                )
                decision.raise_for_status()
                advance = ctx.client.post(
                    f"/api/v1/processes/{ctx.process_id}/advance",
                    headers=ctx.auth_headers(),
                    json={"idempotency_key": f"e2e-g4b-{uuid.uuid4().hex[:8]}", "max_steps": 6},
                    timeout=180.0,
                )
                advance.raise_for_status()
                body = advance.json()
                stage = body.get("process", {}).get("current_stage")
                adv = body.get("advancement") or {}

        receipts = ctx.client.get(
            "/api/v1/agent2/receipts",
            headers=ctx.auth_headers(),
            params={"process_id": ctx.process_id, "limit": 5},
        )
        receipt_rows = receipts.json() if receipts.status_code == 200 else []
        if receipt_rows:
            ctx.receipt_id = str(receipt_rows[0].get("id") or receipt_rows[0].get("receipt_id") or "")

        exec_ok = stage in {"INVOICE_MATCHING", "COMPLETED", "WORKFLOW_EXECUTION"}
        actions = adv.get("autonomous_actions") or []
        executed = any(
            a.get("action") in {"EXECUTE_WORKFLOW", "EXECUTE_PO_DRAFT", "EXECUTE_TASK"}
            and a.get("success")
            for a in actions
        )
        passed = exec_ok or executed or bool(ctx.receipt_id)
        detail = f"stage={stage} receipt={bool(ctx.receipt_id)} executed={executed}"
        ids = f"process={ctx.process_id} receipt={ctx.receipt_id or '—'}"
    except Exception as exc:
        passed = False
        detail = str(exc)
        ids = f"process={ctx.process_id or '—'}"
    ctx.record("G4", "Agent 2 auto execution", passed, started, detail=detail, ids=ids)


def gate_g5_risk_policy(ctx: SmokeContext) -> None:
    started = time.perf_counter()
    if not ctx.process_id:
        ctx.record("G5", "Agent 4 risk / policy", False, started, detail="no process_id")
        return
    try:
        process = ctx.client.get(
            f"/api/v1/processes/{ctx.process_id}",
            headers=ctx.auth_headers(),
        )
        process.raise_for_status()
        stage = process.json().get("current_stage")
        approvals = ctx.client.get("/api/v1/approvals", headers=ctx.auth_headers())
        related = [
            row for row in (approvals.json() if approvals.status_code == 200 else [])
            if str(row.get("process_id")) == ctx.process_id
        ]
        passed = stage in {
            "AWAITING_HUMAN_APPROVAL",
            "WORKFLOW_EXECUTION",
            "INVOICE_MATCHING",
            "COMPLETED",
        } or len(related) >= 1
        detail = f"stage={stage} approvals={len(related)}"
        ids = f"process={ctx.process_id}"
    except Exception as exc:
        passed = False
        detail = str(exc)
        ids = f"process={ctx.process_id}"
    ctx.record("G5", "Agent 4 risk / approval gate", passed, started, detail=detail, ids=ids)


def gate_g6_messaging(ctx: SmokeContext) -> None:
    started = time.perf_counter()
    if not ctx.process_id:
        ctx.record("G6", "Inter-agent messaging audit", False, started, detail="no process_id")
        return
    try:
        settings = _load_settings()
        service_key = (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip()
        base = (settings.SUPABASE_URL or "").rstrip("/")
        message_count = 0
        if service_key and base:
            rest = httpx.get(
                f"{base}/rest/v1/agent_messages",
                headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
                params={
                    "process_id": f"eq.{ctx.process_id}",
                    "select": "id,from_agent,to_agent,message_type",
                },
                timeout=20.0,
            )
            if rest.status_code == 200:
                message_count = len(rest.json())

        audit = ctx.client.get(
            "/api/v1/audit",
            headers=ctx.auth_headers(),
            params={"entity_id": ctx.process_id, "limit": 20},
        )
        audit_count = len(audit.json()) if audit.status_code == 200 else 0
        passed = message_count >= 2 or audit_count >= 1
        detail = f"agent_messages={message_count} audit_logs={audit_count}"
        ids = f"process={ctx.process_id}"
    except Exception as exc:
        passed = False
        detail = str(exc)
        ids = f"process={ctx.process_id}"
    ctx.record("G6", "Inter-agent messaging audit", passed, started, detail=detail, ids=ids)


def gate_g7_golden_path(ctx: SmokeContext) -> None:
    started = time.perf_counter()
    if not ctx.process_id:
        ctx.record("G7", "Golden path completion", False, started, detail="no process_id")
        return
    try:
        process = ctx.client.get(
            f"/api/v1/processes/{ctx.process_id}",
            headers=ctx.auth_headers(),
        )
        process.raise_for_status()
        stage = process.json().get("current_stage")
        meta = process.json().get("metadata_json") or {}

        if stage == "INVOICE_MATCHING":
            po_ref = (
                meta.get("po_reference")
                or (meta.get("purchase_order") or {}).get("po_number")
                or "PO-E2E-001"
            )
            amount = meta.get("amount") or (meta.get("purchase_order") or {}).get("amount") or 2500.0
            complete = ctx.client.post(
                f"/api/v1/processes/{ctx.process_id}/complete-invoice-matching",
                headers=ctx.auth_headers(),
                json={
                    "invoice_number": "INV-E2E-001",
                    "amount": float(amount) if amount is not None else 2500.0,
                    "currency": "USD",
                    "po_reference": po_ref,
                    "expected_invoice_number": "INV-E2E-001",
                    "expected_amount": float(amount) if amount is not None else 2500.0,
                    "expected_currency": "USD",
                    "expected_po_reference": po_ref,
                },
                timeout=60.0,
            )
            complete.raise_for_status()
            stage = complete.json().get("current_stage")

        if stage != "COMPLETED":
            advance = ctx.client.post(
                f"/api/v1/processes/{ctx.process_id}/advance",
                headers=ctx.auth_headers(),
                json={
                    "idempotency_key": f"e2e-g7-{uuid.uuid4().hex[:8]}",
                    "max_steps": 4,
                    "invoice": {
                        "invoice_number": "INV-E2E-001",
                        "amount": 2500.0,
                        "currency": "USD",
                        "expected_invoice_number": "INV-E2E-001",
                        "expected_amount": 2500.0,
                        "expected_currency": "USD",
                    },
                },
                timeout=120.0,
            )
            if advance.status_code == 200:
                stage = advance.json().get("process", {}).get("current_stage")

        passed = stage == "COMPLETED"
        detail = f"final_stage={stage}"
        ids = f"process={ctx.process_id}"
    except Exception as exc:
        passed = False
        detail = str(exc)
        ids = f"process={ctx.process_id}"
    ctx.record("G7", "Golden path completion", passed, started, detail=detail, ids=ids)


def gate_g8_ui_truth(ctx: SmokeContext) -> None:
    started = time.perf_counter()
    try:
        samples: list[str] = []
        for path in ("/health", "/api/v1/processes"):
            response = ctx.client.get(path, headers=ctx.auth_headers())
            samples.append(response.text.lower())
        leaked = [marker for marker in FORBIDDEN_RESPONSE_MARKERS if any(marker in s for s in samples)]
        process_ok = True
        if ctx.process_id:
            proc = ctx.client.get(
                f"/api/v1/processes/{ctx.process_id}",
                headers=ctx.auth_headers(),
            )
            if proc.status_code == 200:
                body = proc.json()
                process_ok = bool(body.get("id")) and body.get("current_stage") not in {None, ""}
            else:
                process_ok = False
        passed = not leaked and process_ok
        detail = f"forbidden={leaked or 'none'} process_ok={process_ok}"
        ids = f"process={ctx.process_id or '—'}"
    except Exception as exc:
        passed = False
        detail = str(exc)
        ids = f"process={ctx.process_id or '—'}"
    ctx.record("G8", "API truth / no mock markers", passed, started, detail=detail, ids=ids)


def _print_table(results: list[GateResult]) -> None:
    print()
    print("E2E smoke — gate results")
    print("-" * 88)
    print(f"{'Gate':<6} {'Check':<32} {'Status':<7} {'ms':>8}  {'IDs / detail'}")
    print("-" * 88)
    for row in results:
        status = "PASS" if row.passed else "FAIL"
        tail = row.ids or row.detail
        if row.ids and row.detail:
            tail = f"{row.ids} | {row.detail}"
        print(f"{row.gate:<6} {row.check:<32} {status:<7} {row.elapsed_ms:>8.0f}  {tail}")
    print("-" * 88)
    passed = sum(1 for r in results if r.passed)
    print(f"Summary: {passed}/{len(results)} passed")
    print()


def run_smoke(base_url: str) -> int:
    settings = _load_settings()
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=60.0) as client:
        requester, approver = _resolve_tokens(client, settings)
        ctx = SmokeContext(
            base_url=base_url,
            client=client,
            requester_token=requester,
            approver_token=approver,
        )
        gate_g1_health(ctx)
        gate_g2_discovery(ctx)
        gate_g3_resource_planning(ctx)
        gate_g4_execution(ctx)
        gate_g5_risk_policy(ctx)
        gate_g6_messaging(ctx)
        gate_g7_golden_path(ctx)
        gate_g8_ui_truth(ctx)
        _print_table(ctx.results)
        return 0 if all(r.passed for r in ctx.results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="BPMFlow E2E smoke (G1–G8)")
    parser.add_argument("--base-url", default=os.environ.get("E2E_BASE_URL", DEFAULT_BASE))
    parser.add_argument(
        "--cold-start",
        action="store_true",
        help="Apply migrations, seed demo tenant, start uvicorn, then run smoke",
    )
    args = parser.parse_args()

    server: subprocess.Popen[Any] | None = None
    try:
        if args.cold_start:
            server = _cold_start(args.base_url)
        else:
            _wait_for_health(args.base_url, timeout_seconds=15.0)
        return run_smoke(args.base_url)
    except Exception as exc:
        print(f"E2E smoke aborted: {exc}", file=sys.stderr)
        return 1
    finally:
        if server is not None and server.poll() is None:
            server.send_signal(signal.SIGTERM)
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
