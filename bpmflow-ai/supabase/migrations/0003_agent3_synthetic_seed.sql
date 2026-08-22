-- Agent 3 synthetic seed data for development/test read-path validation
-- Migration number 0003 — Agent 3 owned
-- Deterministic, idempotent synthetic records only. No real PII.

-- =============================================================================
-- A. Demo tenants
-- =============================================================================

INSERT INTO public.tenants (id, code, name, is_active)
VALUES
    (
        '00000000-0000-0000-0000-000000000001',
        'AGENT3_DEMO',
        'Synthetic Agent 3 Demo Tenant',
        TRUE
    ),
    (
        '00000000-0000-0000-0000-000000000002',
        'AGENT3_OTHER',
        'Synthetic Agent 3 Other Tenant',
        TRUE
    )
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- B. Lookup catalogs (demo tenant)
-- =============================================================================

INSERT INTO public.roles (id, tenant_id, code, name)
VALUES
    ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000001', 'developer', 'Synthetic Developer Role'),
    ('00000000-0000-0000-0000-000000000102', '00000000-0000-0000-0000-000000000001', 'approver', 'Synthetic Approver Role')
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.skills (id, tenant_id, code, name)
VALUES
    ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000001', 'python', 'Synthetic Python Skill'),
    ('00000000-0000-0000-0000-000000000202', '00000000-0000-0000-0000-000000000001', 'fastapi', 'Synthetic FastAPI Skill'),
    ('00000000-0000-0000-0000-000000000203', '00000000-0000-0000-0000-000000000001', 'kubernetes', 'Synthetic Kubernetes Skill')
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.authorities (id, tenant_id, code, name)
VALUES
    ('00000000-0000-0000-0000-000000000301', '00000000-0000-0000-0000-000000000001', 'senior', 'Synthetic Senior Authority'),
    ('00000000-0000-0000-0000-000000000302', '00000000-0000-0000-0000-000000000001', 'standard', 'Synthetic Standard Authority')
ON CONFLICT (id) DO NOTHING;

-- =============================================================================
-- C. HUMAN resources (6 scenarios)
-- =============================================================================

INSERT INTO public.resources (
    id, tenant_id, name, type, is_active, employee_identifier,
    capacity, availability_percentage, cost_per_hour, department, skills
) VALUES
    (
        '00000000-0000-0000-0000-000000000010',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Employee Alpha',
        'HUMAN', TRUE, 'SYN-EMP-010',
        1, 100, 0.00, 'SYN-DEP-OPS', ARRAY['python', 'fastapi']
    ),
    (
        '00000000-0000-0000-0000-000000000011',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Employee Beta',
        'HUMAN', TRUE, 'SYN-EMP-011',
        1, 100, 0.00, 'SYN-DEP-OPS', ARRAY['python']
    ),
    (
        '00000000-0000-0000-0000-000000000012',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Employee Gamma',
        'HUMAN', TRUE, 'SYN-EMP-012',
        1, 100, 0.00, 'SYN-DEP-OPS', ARRAY['python', 'fastapi']
    ),
    (
        '00000000-0000-0000-0000-000000000013',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Employee Delta',
        'HUMAN', TRUE, 'SYN-EMP-013',
        1, 100, 0.00, 'SYN-DEP-OPS', ARRAY['python', 'fastapi']
    ),
    (
        '00000000-0000-0000-0000-000000000014',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Employee Epsilon',
        'HUMAN', TRUE, 'SYN-EMP-014',
        1, 100, 0.00, 'SYN-DEP-OPS', ARRAY['python', 'fastapi']
    ),
    (
        '00000000-0000-0000-0000-000000000015',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Employee Zeta',
        'HUMAN', FALSE, 'SYN-EMP-015',
        1, 0, 0.00, 'SYN-DEP-OPS', ARRAY['python', 'fastapi']
    ),
    (
        '00000000-0000-0000-0000-000000000016',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Employee Sod Target',
        'HUMAN', TRUE, 'SYN-EMP-016',
        1, 100, 0.00, 'SYN-DEP-FIN', ARRAY['python']
    )
ON CONFLICT (id) DO UPDATE SET
    tenant_id = EXCLUDED.tenant_id,
    name = EXCLUDED.name,
    type = EXCLUDED.type,
    is_active = EXCLUDED.is_active,
    employee_identifier = EXCLUDED.employee_identifier,
    department = EXCLUDED.department,
    skills = EXCLUDED.skills;

-- Cross-tenant isolation resource (other tenant)
INSERT INTO public.resources (
    id, tenant_id, name, type, is_active, employee_identifier,
    capacity, availability_percentage, cost_per_hour, department, skills
) VALUES (
    '00000000-0000-0000-0000-000000000030',
    '00000000-0000-0000-0000-000000000002',
    'Synthetic Employee Other Tenant',
    'HUMAN', TRUE, 'SYN-EMP-030',
    1, 100, 0.00, 'SYN-DEP-OTHER', ARRAY['python']
)
ON CONFLICT (id) DO UPDATE SET
    tenant_id = EXCLUDED.tenant_id,
    name = EXCLUDED.name,
    type = EXCLUDED.type,
    is_active = EXCLUDED.is_active;

-- =============================================================================
-- D. BUDGET resources (2 scenarios)
-- =============================================================================

INSERT INTO public.resources (
    id, tenant_id, name, type, is_active,
    capacity, availability_percentage, cost_per_hour, department, skills
) VALUES
    (
        '00000000-0000-0000-0000-000000000020',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Budget Valid',
        'BUDGET', TRUE,
        NULL, 100, 0.00, 'SYN-DEP-FIN', ARRAY[]::TEXT[]
    ),
    (
        '00000000-0000-0000-0000-000000000021',
        '00000000-0000-0000-0000-000000000001',
        'Synthetic Budget Invalid',
        'BUDGET', TRUE,
        NULL, 100, 0.00, 'SYN-DEP-FIN', ARRAY[]::TEXT[]
    )
ON CONFLICT (id) DO UPDATE SET
    tenant_id = EXCLUDED.tenant_id,
    name = EXCLUDED.name,
    type = EXCLUDED.type,
    is_active = EXCLUDED.is_active;

-- =============================================================================
-- E. Junction mappings
-- =============================================================================

INSERT INTO public.resource_roles (tenant_id, resource_id, role_id, is_primary)
VALUES
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000101', TRUE),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000101', TRUE),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000012', '00000000-0000-0000-0000-000000000101', TRUE),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-000000000101', TRUE),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000014', '00000000-0000-0000-0000-000000000101', TRUE),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000015', '00000000-0000-0000-0000-000000000101', TRUE),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000016', '00000000-0000-0000-0000-000000000102', TRUE)
ON CONFLICT (tenant_id, resource_id, role_id) DO NOTHING;

INSERT INTO public.resource_skills (tenant_id, resource_id, skill_id, proficiency, certified_at)
VALUES
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000201', 90.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000202', 85.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000201', 80.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000012', '00000000-0000-0000-0000-000000000201', 80.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000012', '00000000-0000-0000-0000-000000000202', 75.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-000000000201', 80.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-000000000202', 75.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000014', '00000000-0000-0000-0000-000000000201', 80.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000014', '00000000-0000-0000-0000-000000000202', 75.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000015', '00000000-0000-0000-0000-000000000201', 80.00, TIMESTAMPTZ '2025-06-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000015', '00000000-0000-0000-0000-000000000202', 75.00, TIMESTAMPTZ '2025-06-01 12:00:00+00')
ON CONFLICT (tenant_id, resource_id, skill_id) DO NOTHING;

INSERT INTO public.resource_authorities (tenant_id, resource_id, authority_id, granted_at, valid_until)
VALUES
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000301', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000301', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000012', '00000000-0000-0000-0000-000000000301', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000013', '00000000-0000-0000-0000-000000000301', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000014', '00000000-0000-0000-0000-000000000301', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000015', '00000000-0000-0000-0000-000000000301', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL)
ON CONFLICT (tenant_id, resource_id, authority_id) DO NOTHING;

-- =============================================================================
-- F. Human profiles
-- =============================================================================

INSERT INTO public.human_resource_profiles (
    tenant_id, resource_id, max_workload_pct, evidence_checked_at, evidence_valid_until
) VALUES
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000010', 80.00, TIMESTAMPTZ '2025-12-01 12:00:00+00', TIMESTAMPTZ '2026-12-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000011', 80.00, TIMESTAMPTZ '2025-12-01 12:00:00+00', TIMESTAMPTZ '2026-12-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000012', 80.00, TIMESTAMPTZ '2025-12-01 12:00:00+00', TIMESTAMPTZ '2026-12-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000013', 90.00, TIMESTAMPTZ '2025-12-01 12:00:00+00', TIMESTAMPTZ '2026-12-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000014', 80.00, TIMESTAMPTZ '2025-12-01 12:00:00+00', TIMESTAMPTZ '2026-12-01 12:00:00+00'),
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000015', 80.00, TIMESTAMPTZ '2025-12-01 12:00:00+00', TIMESTAMPTZ '2026-12-01 12:00:00+00')
ON CONFLICT (tenant_id, resource_id) DO UPDATE SET
    max_workload_pct = EXCLUDED.max_workload_pct,
    evidence_checked_at = EXCLUDED.evidence_checked_at,
    evidence_valid_until = EXCLUDED.evidence_valid_until;

-- =============================================================================
-- G. Availability windows
-- =============================================================================

INSERT INTO public.resource_availability (
    id, tenant_id, resource_id, available_from, available_until, reason
) VALUES
    ('00000000-0000-0000-0000-000000000501', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000010', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL, 'Synthetic open availability'),
    ('00000000-0000-0000-0000-000000000502', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000011', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL, 'Synthetic open availability'),
    ('00000000-0000-0000-0000-000000000503', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000012', TIMESTAMPTZ '2026-06-01 00:00:00+00', NULL, 'Synthetic future availability'),
    ('00000000-0000-0000-0000-000000000504', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000013', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL, 'Synthetic open availability'),
    ('00000000-0000-0000-0000-000000000505', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000014', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL, 'Synthetic open availability'),
    ('00000000-0000-0000-0000-000000000506', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000015', TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL, 'Synthetic open availability')
ON CONFLICT (id) DO UPDATE SET
    available_from = EXCLUDED.available_from,
    available_until = EXCLUDED.available_until,
    reason = EXCLUDED.reason;

-- =============================================================================
-- H. Workload snapshots (no projected column)
-- =============================================================================

INSERT INTO public.workload_snapshots (
    id, tenant_id, resource_id, snapshot_at, current_workload_pct, max_workload_pct
) VALUES
    ('00000000-0000-0000-0000-000000000601', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000010', TIMESTAMPTZ '2025-06-01 12:00:00+00', 50.00, 80.00),
    ('00000000-0000-0000-0000-000000000602', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000010', TIMESTAMPTZ '2025-12-01 12:00:00+00', 35.00, 80.00),
    ('00000000-0000-0000-0000-000000000603', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000011', TIMESTAMPTZ '2025-12-01 12:00:00+00', 40.00, 80.00),
    ('00000000-0000-0000-0000-000000000604', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000012', TIMESTAMPTZ '2025-12-01 12:00:00+00', 30.00, 80.00),
    ('00000000-0000-0000-0000-000000000605', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000013', TIMESTAMPTZ '2025-12-01 12:00:00+00', 88.00, 90.00),
    ('00000000-0000-0000-0000-000000000606', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000014', TIMESTAMPTZ '2025-12-01 12:00:00+00', 45.00, 80.00),
    ('00000000-0000-0000-0000-000000000607', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000015', TIMESTAMPTZ '2025-12-01 12:00:00+00', 20.00, 80.00)
ON CONFLICT (id) DO UPDATE SET
    snapshot_at = EXCLUDED.snapshot_at,
    current_workload_pct = EXCLUDED.current_workload_pct,
    max_workload_pct = EXCLUDED.max_workload_pct;

-- =============================================================================
-- I. Budget profiles
-- =============================================================================

INSERT INTO public.budget_resource_profiles (
    tenant_id, resource_id, cost_centre, currency, available_balance,
    authorization_limit, valid_from, valid_until, evidence_checked_at, evidence_valid_until
) VALUES
    (
        '00000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000020',
        'CC-DEMO', 'USD', 50000.00, 25000.00,
        TIMESTAMPTZ '2025-01-01 00:00:00+00', TIMESTAMPTZ '2026-12-31 23:59:59+00',
        TIMESTAMPTZ '2025-12-01 12:00:00+00', TIMESTAMPTZ '2026-12-01 12:00:00+00'
    ),
    (
        '00000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000021',
        'CC-INVALID', 'USD', 100.00, 50.00,
        TIMESTAMPTZ '2025-01-01 00:00:00+00', TIMESTAMPTZ '2026-12-31 23:59:59+00',
        TIMESTAMPTZ '2025-12-01 12:00:00+00', TIMESTAMPTZ '2026-12-01 12:00:00+00'
    )
ON CONFLICT (tenant_id, resource_id) DO UPDATE SET
    cost_centre = EXCLUDED.cost_centre,
    available_balance = EXCLUDED.available_balance,
    authorization_limit = EXCLUDED.authorization_limit,
    valid_from = EXCLUDED.valid_from,
    valid_until = EXCLUDED.valid_until,
    evidence_checked_at = EXCLUDED.evidence_checked_at,
    evidence_valid_until = EXCLUDED.evidence_valid_until;

-- =============================================================================
-- J. Evidence references
-- =============================================================================

INSERT INTO public.evidence_references (
    id, tenant_id, resource_id, evidence_key, payload, checked_at, valid_until
) VALUES
    (
        '00000000-0000-0000-0000-000000000701',
        '00000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000010',
        'hr_profile',
        '{"source":"agent3_synthetic_seed","scenario":"eligible"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    ),
    (
        '00000000-0000-0000-0000-000000000702',
        '00000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000020',
        'budget_profile',
        '{"source":"agent3_synthetic_seed","scenario":"valid_budget"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    ),
    (
        '00000000-0000-0000-0000-000000000703',
        '00000000-0000-0000-0000-000000000001',
        '00000000-0000-0000-0000-000000000021',
        'budget_profile',
        '{"source":"agent3_synthetic_seed","scenario":"invalid_budget"}'::jsonb,
        TIMESTAMPTZ '2025-12-01 12:00:00+00',
        TIMESTAMPTZ '2026-12-01 12:00:00+00'
    )
ON CONFLICT (tenant_id, resource_id, evidence_key) DO UPDATE SET
    payload = EXCLUDED.payload,
    checked_at = EXCLUDED.checked_at,
    valid_until = EXCLUDED.valid_until;

-- =============================================================================
-- K. SoD rule and declared conflict
-- =============================================================================

INSERT INTO public.sod_rules (
    id, tenant_id, process_stage,
    first_role_code, conflicting_role_code, reason, is_active
) VALUES (
    '00000000-0000-0000-0000-000000000401',
    '00000000-0000-0000-0000-000000000001',
    'resource_allocation',
    'developer', 'approver',
    'Synthetic SoD: developer cannot also hold approver role in same stage',
    TRUE
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.resource_declared_conflicts (
    id, tenant_id, resource_id, conflicting_resource_id, reason, valid_from, valid_until
) VALUES (
    '00000000-0000-0000-0000-000000000801',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000014',
    '00000000-0000-0000-0000-000000000016',
    'Synthetic declared SoD conflict between epsilon and sod target',
    TIMESTAMPTZ '2025-01-01 00:00:00+00',
    NULL
)
ON CONFLICT (id) DO NOTHING;
