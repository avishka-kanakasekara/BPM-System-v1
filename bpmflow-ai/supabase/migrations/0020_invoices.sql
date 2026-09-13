-- Phase 8C: tenant-scoped invoices and invoice items.
-- Matching is PO ↔ Invoice. There is no goods-receipt table.

CREATE TABLE IF NOT EXISTS public.invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    invoice_number TEXT NOT NULL,
    vendor_id UUID NOT NULL,
    purchase_order_id UUID NOT NULL,
    process_id UUID NOT NULL,
    invoice_date DATE,
    currency TEXT NOT NULL,
    subtotal NUMERIC(18, 2) NOT NULL DEFAULT 0,
    tax NUMERIC(18, 2) NOT NULL DEFAULT 0,
    total NUMERIC(18, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'RECEIVED',
    received_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    evidence_id TEXT,
    document_id UUID,
    match_result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    workflow_step_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT invoices_status_check CHECK (
        status IN ('RECEIVED', 'MATCHING', 'MATCHED', 'MISMATCH', 'EXCEPTION', 'CANCELLED')
    ),
    CONSTRAINT invoices_currency_check CHECK (char_length(btrim(currency)) >= 3),
    CONSTRAINT invoices_amounts_non_negative CHECK (
        subtotal >= 0 AND tax >= 0 AND total >= 0
    ),
    CONSTRAINT invoices_number_not_blank CHECK (char_length(btrim(invoice_number)) > 0),
    CONSTRAINT invoices_tenant_number_unique UNIQUE (tenant_id, invoice_number),
    CONSTRAINT invoices_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT invoices_vendor_tenant_fkey
        FOREIGN KEY (tenant_id, vendor_id)
        REFERENCES public.vendors (tenant_id, id),
    CONSTRAINT invoices_po_tenant_fkey
        FOREIGN KEY (tenant_id, purchase_order_id)
        REFERENCES public.purchase_orders (tenant_id, id),
    CONSTRAINT invoices_process_tenant_fkey
        FOREIGN KEY (tenant_id, process_id)
        REFERENCES public.processes (tenant_id, id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_invoices_tenant_process
    ON public.invoices (tenant_id, process_id);
CREATE INDEX IF NOT EXISTS idx_invoices_tenant_po
    ON public.invoices (tenant_id, purchase_order_id);

CREATE TABLE IF NOT EXISTS public.invoice_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    invoice_id UUID NOT NULL,
    description TEXT NOT NULL,
    quantity NUMERIC(18, 4) NOT NULL,
    unit_price NUMERIC(18, 2) NOT NULL,
    line_total NUMERIC(18, 2) NOT NULL,
    purchase_order_item_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT invoice_items_qty_positive CHECK (quantity > 0),
    CONSTRAINT invoice_items_price_non_negative CHECK (unit_price >= 0 AND line_total >= 0),
    CONSTRAINT invoice_items_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT invoice_items_invoice_tenant_fkey
        FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES public.invoices (tenant_id, id)
        ON DELETE CASCADE,
    CONSTRAINT invoice_items_po_item_tenant_fkey
        FOREIGN KEY (tenant_id, purchase_order_item_id)
        REFERENCES public.purchase_order_items (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_invoice_items_tenant_invoice
    ON public.invoice_items (tenant_id, invoice_id);

COMMENT ON TABLE public.invoices IS
    'Authoritative vendor invoices. Matching is deterministic PO ↔ Invoice. metadata_json is not the source of truth.';
COMMENT ON COLUMN public.invoices.match_result_json IS
    'Structured InvoiceMatchResult. Amount comparison is exact NUMERIC cents unless policy sets invoice_amount_tolerance.';

ALTER TABLE public.invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invoice_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS invoices_service_role ON public.invoices;
CREATE POLICY invoices_service_role ON public.invoices FOR ALL TO service_role
    USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS invoice_items_service_role ON public.invoice_items;
CREATE POLICY invoice_items_service_role ON public.invoice_items FOR ALL TO service_role
    USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS invoices_tenant_authenticated ON public.invoices;
CREATE POLICY invoices_tenant_authenticated ON public.invoices FOR SELECT TO authenticated
    USING (tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', ''));
DROP POLICY IF EXISTS invoice_items_tenant_authenticated ON public.invoice_items;
CREATE POLICY invoice_items_tenant_authenticated ON public.invoice_items FOR SELECT TO authenticated
    USING (tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', ''));

ALTER TABLE public.tool_registry DROP CONSTRAINT IF EXISTS tool_registry_action_check;
ALTER TABLE public.tool_registry ADD CONSTRAINT tool_registry_action_check CHECK (
    action_code IN (
        'CREATE_TASK',
        'UPDATE_TASK',
        'SEND_EMAIL',
        'SEND_REMINDER',
        'CREATE_PURCHASE_ORDER',
        'REQUEST_QUOTATION',
        'UPDATE_PROCUREMENT_RECORD',
        'ESCALATE',
        'CREATE_EXCEPTION',
        'GET_PROCESS_HISTORY',
        'GET_TASK_HISTORY',
        'CALCULATE_KPI',
        'MATCH_INVOICE'
    )
);
