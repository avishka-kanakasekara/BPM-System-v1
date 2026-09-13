-- Phase 8B: tenant-scoped vendors, quotations, and purchase orders.
-- Process + ProcessContext remain the purchase-request root.
-- Does not seed demo rows.

CREATE TABLE IF NOT EXISTS public.vendors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    vendor_code TEXT NOT NULL,
    legal_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    phone TEXT,
    website TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT vendors_status_check CHECK (status IN ('active', 'inactive')),
    CONSTRAINT vendors_code_not_blank CHECK (char_length(btrim(vendor_code)) > 0),
    CONSTRAINT vendors_tenant_code_unique UNIQUE (tenant_id, vendor_code),
    CONSTRAINT vendors_tenant_id_unique UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_vendors_tenant_status
    ON public.vendors (tenant_id, status);

CREATE TABLE IF NOT EXISTS public.vendor_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    vendor_id UUID NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    title TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT vendor_contacts_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT vendor_contacts_vendor_tenant_fkey
        FOREIGN KEY (tenant_id, vendor_id)
        REFERENCES public.vendors (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_vendor_contacts_tenant_vendor
    ON public.vendor_contacts (tenant_id, vendor_id);

CREATE TABLE IF NOT EXISTS public.quotations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    quotation_number TEXT NOT NULL,
    vendor_id UUID NOT NULL,
    process_id UUID NOT NULL,
    quotation_date DATE,
    currency TEXT NOT NULL,
    subtotal NUMERIC(18, 2) NOT NULL DEFAULT 0,
    tax NUMERIC(18, 2) NOT NULL DEFAULT 0,
    total NUMERIC(18, 2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'RECEIVED',
    evidence_id TEXT,
    document_id UUID,
    workflow_step_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT quotations_status_check CHECK (
        status IN ('REQUESTED', 'RECEIVED', 'SELECTED', 'REJECTED', 'CANCELLED')
    ),
    CONSTRAINT quotations_currency_check CHECK (char_length(btrim(currency)) >= 3),
    CONSTRAINT quotations_amounts_non_negative CHECK (
        subtotal >= 0 AND tax >= 0 AND total >= 0
    ),
    CONSTRAINT quotations_tenant_number_unique UNIQUE (tenant_id, quotation_number),
    CONSTRAINT quotations_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT quotations_vendor_tenant_fkey
        FOREIGN KEY (tenant_id, vendor_id)
        REFERENCES public.vendors (tenant_id, id),
    CONSTRAINT quotations_process_tenant_fkey
        FOREIGN KEY (tenant_id, process_id)
        REFERENCES public.processes (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_quotations_tenant_process
    ON public.quotations (tenant_id, process_id);

CREATE TABLE IF NOT EXISTS public.quotation_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    quotation_id UUID NOT NULL,
    description TEXT NOT NULL,
    quantity NUMERIC(18, 4) NOT NULL,
    unit_price NUMERIC(18, 2) NOT NULL,
    line_total NUMERIC(18, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT quotation_items_qty_positive CHECK (quantity > 0),
    CONSTRAINT quotation_items_price_non_negative CHECK (unit_price >= 0 AND line_total >= 0),
    CONSTRAINT quotation_items_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT quotation_items_quotation_tenant_fkey
        FOREIGN KEY (tenant_id, quotation_id)
        REFERENCES public.quotations (tenant_id, id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS quotation_items_tenant_id_unique
    ON public.quotation_items (tenant_id, id);

CREATE INDEX IF NOT EXISTS idx_quotation_items_tenant_quotation
    ON public.quotation_items (tenant_id, quotation_id);

CREATE TABLE IF NOT EXISTS public.purchase_order_sequences (
    tenant_id UUID PRIMARY KEY REFERENCES public.tenants(id),
    next_value INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT purchase_order_sequences_next_positive CHECK (next_value >= 1)
);

CREATE TABLE IF NOT EXISTS public.purchase_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    po_number TEXT NOT NULL,
    process_id UUID NOT NULL,
    vendor_id UUID NOT NULL,
    workflow_plan_id UUID,
    workflow_step_id UUID,
    currency TEXT NOT NULL,
    subtotal NUMERIC(18, 2) NOT NULL,
    tax NUMERIC(18, 2) NOT NULL DEFAULT 0,
    total NUMERIC(18, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    created_by TEXT,
    selected_quotation_id UUID,
    notes TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT purchase_orders_status_check CHECK (
        status IN ('DRAFT', 'ISSUED', 'CANCELLED')
    ),
    CONSTRAINT purchase_orders_currency_check CHECK (char_length(btrim(currency)) >= 3),
    CONSTRAINT purchase_orders_amounts_non_negative CHECK (
        subtotal >= 0 AND tax >= 0 AND total >= 0
    ),
    CONSTRAINT purchase_orders_tenant_number_unique UNIQUE (tenant_id, po_number),
    CONSTRAINT purchase_orders_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT purchase_orders_vendor_tenant_fkey
        FOREIGN KEY (tenant_id, vendor_id)
        REFERENCES public.vendors (tenant_id, id),
    CONSTRAINT purchase_orders_process_tenant_fkey
        FOREIGN KEY (tenant_id, process_id)
        REFERENCES public.processes (tenant_id, id)
        ON DELETE CASCADE,
    CONSTRAINT purchase_orders_quotation_tenant_fkey
        FOREIGN KEY (tenant_id, selected_quotation_id)
        REFERENCES public.quotations (tenant_id, id)
);

CREATE UNIQUE INDEX IF NOT EXISTS purchase_orders_one_per_step
    ON public.purchase_orders (tenant_id, workflow_step_id)
    WHERE workflow_step_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_purchase_orders_tenant_process
    ON public.purchase_orders (tenant_id, process_id);

CREATE TABLE IF NOT EXISTS public.purchase_order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    purchase_order_id UUID NOT NULL,
    description TEXT NOT NULL,
    quantity NUMERIC(18, 4) NOT NULL,
    unit_price NUMERIC(18, 2) NOT NULL,
    line_total NUMERIC(18, 2) NOT NULL,
    source_quotation_item_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT purchase_order_items_qty_positive CHECK (quantity > 0),
    CONSTRAINT purchase_order_items_price_non_negative CHECK (unit_price >= 0 AND line_total >= 0),
    CONSTRAINT purchase_order_items_po_tenant_fkey
        FOREIGN KEY (tenant_id, purchase_order_id)
        REFERENCES public.purchase_orders (tenant_id, id)
        ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS purchase_order_items_tenant_id_unique
    ON public.purchase_order_items (tenant_id, id);

CREATE INDEX IF NOT EXISTS idx_purchase_order_items_tenant_po
    ON public.purchase_order_items (tenant_id, purchase_order_id);

COMMENT ON TABLE public.vendors IS
    'Tenant-scoped supplier identity. vendor_code is unique per tenant, not globally.';
COMMENT ON TABLE public.quotations IS
    'Vendor quotations linked to a process. Authoritative quotation count is COUNT(*) not tokens.';
COMMENT ON TABLE public.purchase_orders IS
    'Authoritative purchase orders. process.metadata_json may hold a reference only.';

ALTER TABLE public.vendors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vendor_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.quotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.quotation_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.purchase_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.purchase_order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.purchase_order_sequences ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS vendors_service_role ON public.vendors;
CREATE POLICY vendors_service_role ON public.vendors FOR ALL TO service_role
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS vendor_contacts_service_role ON public.vendor_contacts;
CREATE POLICY vendor_contacts_service_role ON public.vendor_contacts FOR ALL TO service_role
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS quotations_service_role ON public.quotations;
CREATE POLICY quotations_service_role ON public.quotations FOR ALL TO service_role
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS quotation_items_service_role ON public.quotation_items;
CREATE POLICY quotation_items_service_role ON public.quotation_items FOR ALL TO service_role
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS purchase_orders_service_role ON public.purchase_orders;
CREATE POLICY purchase_orders_service_role ON public.purchase_orders FOR ALL TO service_role
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS purchase_order_items_service_role ON public.purchase_order_items;
CREATE POLICY purchase_order_items_service_role ON public.purchase_order_items FOR ALL TO service_role
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS purchase_order_sequences_service_role ON public.purchase_order_sequences;
CREATE POLICY purchase_order_sequences_service_role ON public.purchase_order_sequences FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS vendors_tenant_authenticated ON public.vendors;
CREATE POLICY vendors_tenant_authenticated ON public.vendors FOR SELECT TO authenticated
    USING (tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', ''));
DROP POLICY IF EXISTS vendor_contacts_tenant_authenticated ON public.vendor_contacts;
CREATE POLICY vendor_contacts_tenant_authenticated ON public.vendor_contacts FOR SELECT TO authenticated
    USING (tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', ''));
DROP POLICY IF EXISTS quotations_tenant_authenticated ON public.quotations;
CREATE POLICY quotations_tenant_authenticated ON public.quotations FOR SELECT TO authenticated
    USING (tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', ''));
DROP POLICY IF EXISTS quotation_items_tenant_authenticated ON public.quotation_items;
CREATE POLICY quotation_items_tenant_authenticated ON public.quotation_items FOR SELECT TO authenticated
    USING (tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', ''));
DROP POLICY IF EXISTS purchase_orders_tenant_authenticated ON public.purchase_orders;
CREATE POLICY purchase_orders_tenant_authenticated ON public.purchase_orders FOR SELECT TO authenticated
    USING (tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', ''));
DROP POLICY IF EXISTS purchase_order_items_tenant_authenticated ON public.purchase_order_items;
CREATE POLICY purchase_order_items_tenant_authenticated ON public.purchase_order_items FOR SELECT TO authenticated
    USING (tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', ''));
