-- Phase 2: tenant-scoped company HR directory.
-- Reuses Agent 3 roles/skills/authorities/resources. Does not seed demo rows.

-- =============================================================================
-- Departments
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    manager_employee_id UUID,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT departments_status_check CHECK (status IN ('active', 'inactive')),
    CONSTRAINT departments_tenant_code_unique UNIQUE (tenant_id, code),
    CONSTRAINT departments_tenant_id_unique UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_departments_tenant_status
    ON public.departments (tenant_id, status);

-- =============================================================================
-- Role catalog extensions (reuse public.roles)
-- =============================================================================

ALTER TABLE public.roles
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS department_id UUID,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'roles_status_check'
    ) THEN
        ALTER TABLE public.roles
            ADD CONSTRAINT roles_status_check CHECK (status IN ('active', 'inactive'));
    END IF;
END $$;

-- =============================================================================
-- Employees (company identity — distinct from auth.users and resources)
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.employees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    employee_number TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    department_id UUID NOT NULL,
    role_id UUID NOT NULL,
    manager_employee_id UUID,
    status TEXT NOT NULL DEFAULT 'active',
    resource_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT employees_status_check CHECK (status IN ('active', 'inactive')),
    CONSTRAINT employees_no_self_manager CHECK (
        manager_employee_id IS NULL OR manager_employee_id <> id
    ),
    CONSTRAINT employees_tenant_number_unique UNIQUE (tenant_id, employee_number),
    CONSTRAINT employees_tenant_email_unique UNIQUE (tenant_id, email),
    CONSTRAINT employees_tenant_id_unique UNIQUE (tenant_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_employees_tenant_resource
    ON public.employees (tenant_id, resource_id)
    WHERE resource_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_employees_tenant_department
    ON public.employees (tenant_id, department_id);

CREATE INDEX IF NOT EXISTS idx_employees_tenant_role
    ON public.employees (tenant_id, role_id);

CREATE INDEX IF NOT EXISTS idx_employees_tenant_manager
    ON public.employees (tenant_id, manager_employee_id);

ALTER TABLE public.employees
    DROP CONSTRAINT IF EXISTS employees_department_fkey;
ALTER TABLE public.employees
    ADD CONSTRAINT employees_department_fkey
        FOREIGN KEY (tenant_id, department_id)
        REFERENCES public.departments(tenant_id, id);

ALTER TABLE public.employees
    DROP CONSTRAINT IF EXISTS employees_role_fkey;
ALTER TABLE public.employees
    ADD CONSTRAINT employees_role_fkey
        FOREIGN KEY (tenant_id, role_id)
        REFERENCES public.roles(tenant_id, id);

ALTER TABLE public.employees
    DROP CONSTRAINT IF EXISTS employees_manager_fkey;
ALTER TABLE public.employees
    ADD CONSTRAINT employees_manager_fkey
        FOREIGN KEY (tenant_id, manager_employee_id)
        REFERENCES public.employees(tenant_id, id);

ALTER TABLE public.employees
    DROP CONSTRAINT IF EXISTS employees_resource_fkey;
ALTER TABLE public.employees
    ADD CONSTRAINT employees_resource_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id);

ALTER TABLE public.departments
    DROP CONSTRAINT IF EXISTS departments_manager_fkey;
ALTER TABLE public.departments
    ADD CONSTRAINT departments_manager_fkey
        FOREIGN KEY (tenant_id, manager_employee_id)
        REFERENCES public.employees(tenant_id, id);

ALTER TABLE public.roles
    DROP CONSTRAINT IF EXISTS roles_department_fkey;
ALTER TABLE public.roles
    ADD CONSTRAINT roles_department_fkey
        FOREIGN KEY (tenant_id, department_id)
        REFERENCES public.departments(tenant_id, id);

-- Prevent circular manager chains (same tenant only).
CREATE OR REPLACE FUNCTION public.prevent_employee_manager_cycle()
RETURNS TRIGGER AS $$
DECLARE
    cursor_id UUID;
    hops INTEGER := 0;
BEGIN
    IF NEW.manager_employee_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF NEW.manager_employee_id = NEW.id THEN
        RAISE EXCEPTION 'employee cannot manage themselves';
    END IF;
    cursor_id := NEW.manager_employee_id;
    WHILE cursor_id IS NOT NULL LOOP
        hops := hops + 1;
        IF hops > 64 THEN
            RAISE EXCEPTION 'manager chain exceeds maximum depth';
        END IF;
        IF cursor_id = NEW.id THEN
            RAISE EXCEPTION 'circular manager relationship is not allowed';
        END IF;
        SELECT e.manager_employee_id INTO cursor_id
        FROM public.employees e
        WHERE e.tenant_id = NEW.tenant_id AND e.id = cursor_id;
    END LOOP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS employees_manager_cycle_guard ON public.employees;
CREATE TRIGGER employees_manager_cycle_guard
    BEFORE INSERT OR UPDATE OF manager_employee_id ON public.employees
    FOR EACH ROW EXECUTE FUNCTION public.prevent_employee_manager_cycle();

-- =============================================================================
-- Approval authority matrix (WHO may approve — not WHEN policy requires it)
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.approval_authorities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    employee_id UUID,
    role_id UUID,
    department_id UUID,
    approval_type TEXT NOT NULL,
    authority_code TEXT,
    max_amount NUMERIC(18, 2) NOT NULL,
    currency TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT approval_authorities_amount_non_negative CHECK (max_amount >= 0),
    CONSTRAINT approval_authorities_subject_check CHECK (
        employee_id IS NOT NULL OR role_id IS NOT NULL
    ),
    CONSTRAINT approval_authorities_tenant_id_unique UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_approval_authorities_tenant_type_active
    ON public.approval_authorities (tenant_id, approval_type, is_active);

ALTER TABLE public.approval_authorities
    DROP CONSTRAINT IF EXISTS approval_authorities_employee_fkey;
ALTER TABLE public.approval_authorities
    ADD CONSTRAINT approval_authorities_employee_fkey
        FOREIGN KEY (tenant_id, employee_id)
        REFERENCES public.employees(tenant_id, id) ON DELETE CASCADE;

ALTER TABLE public.approval_authorities
    DROP CONSTRAINT IF EXISTS approval_authorities_role_fkey;
ALTER TABLE public.approval_authorities
    ADD CONSTRAINT approval_authorities_role_fkey
        FOREIGN KEY (tenant_id, role_id)
        REFERENCES public.roles(tenant_id, id) ON DELETE CASCADE;

ALTER TABLE public.approval_authorities
    DROP CONSTRAINT IF EXISTS approval_authorities_department_fkey;
ALTER TABLE public.approval_authorities
    ADD CONSTRAINT approval_authorities_department_fkey
        FOREIGN KEY (tenant_id, department_id)
        REFERENCES public.departments(tenant_id, id);

-- =============================================================================
-- Identity links: auth user ↔ employee ↔ resource (IDs remain distinct)
-- =============================================================================

ALTER TABLE public.identity_links
    ADD COLUMN IF NOT EXISTS employee_id UUID,
    ADD COLUMN IF NOT EXISTS resource_id UUID;

UPDATE public.identity_links
SET resource_id = employee_resource_id
WHERE resource_id IS NULL AND employee_resource_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_identity_links_employee
    ON public.identity_links (tenant_id, employee_id)
    WHERE employee_id IS NOT NULL;

ALTER TABLE public.identity_links
    DROP CONSTRAINT IF EXISTS identity_links_employee_fkey;
ALTER TABLE public.identity_links
    ADD CONSTRAINT identity_links_employee_fkey
        FOREIGN KEY (tenant_id, employee_id)
        REFERENCES public.employees(tenant_id, id);

ALTER TABLE public.identity_links
    DROP CONSTRAINT IF EXISTS identity_links_resource_tenant_fkey;
ALTER TABLE public.identity_links
    ADD CONSTRAINT identity_links_resource_tenant_fkey
        FOREIGN KEY (tenant_id, resource_id)
        REFERENCES public.resources(tenant_id, id);

-- =============================================================================
-- Budget ownership context (do not redesign budgets)
-- =============================================================================

ALTER TABLE public.budget_resource_profiles
    ADD COLUMN IF NOT EXISTS department_id UUID;

ALTER TABLE public.budget_resource_profiles
    DROP CONSTRAINT IF EXISTS budget_resource_profiles_department_fkey;
ALTER TABLE public.budget_resource_profiles
    ADD CONSTRAINT budget_resource_profiles_department_fkey
        FOREIGN KEY (tenant_id, department_id)
        REFERENCES public.departments(tenant_id, id);

CREATE INDEX IF NOT EXISTS idx_budget_profiles_tenant_department
    ON public.budget_resource_profiles (tenant_id, department_id)
    WHERE department_id IS NOT NULL;

-- =============================================================================
-- RLS — tenant scoped; service_role bypass. Do not add USING (true).
-- =============================================================================

ALTER TABLE public.departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.approval_authorities ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS departments_service_role ON public.departments;
CREATE POLICY departments_service_role
    ON public.departments FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS employees_service_role ON public.employees;
CREATE POLICY employees_service_role
    ON public.employees FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS approval_authorities_service_role ON public.approval_authorities;
CREATE POLICY approval_authorities_service_role
    ON public.approval_authorities FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS departments_tenant_authenticated ON public.departments;
CREATE POLICY departments_tenant_authenticated
    ON public.departments FOR SELECT TO authenticated
    USING (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );

DROP POLICY IF EXISTS employees_tenant_authenticated ON public.employees;
CREATE POLICY employees_tenant_authenticated
    ON public.employees FOR SELECT TO authenticated
    USING (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );

DROP POLICY IF EXISTS approval_authorities_tenant_authenticated ON public.approval_authorities;
CREATE POLICY approval_authorities_tenant_authenticated
    ON public.approval_authorities FOR SELECT TO authenticated
    USING (
        tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );

COMMENT ON TABLE public.employees IS
    'Company HR identity. Distinct from auth.users.id and resources.id.';
COMMENT ON TABLE public.approval_authorities IS
    'Who may approve (limits). Policy knowledge still decides when approval is required.';
