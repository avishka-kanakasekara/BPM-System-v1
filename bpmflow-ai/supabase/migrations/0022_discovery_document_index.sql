-- Phase 9: tenant-scoped discovery documents + retrieval chunks.
-- Extends discovered_documents (Agent 1 ingest) rather than creating a second document store.

ALTER TABLE public.discovered_documents
    ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES public.tenants(id),
    ADD COLUMN IF NOT EXISTS content_hash TEXT,
    ADD COLUMN IF NOT EXISTS source TEXT,
    ADD COLUMN IF NOT EXISTS version TEXT NOT NULL DEFAULT '1',
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS evidence_ref TEXT;

UPDATE public.discovered_documents AS d
SET tenant_id = p.tenant_id
FROM public.processes AS p
WHERE d.process_id = p.id
  AND d.tenant_id IS NULL
  AND p.tenant_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_discovered_documents_tenant_hash
    ON public.discovered_documents (tenant_id, content_hash)
    WHERE content_hash IS NOT NULL AND is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_discovered_documents_tenant_active
    ON public.discovered_documents (tenant_id, is_active);

CREATE TABLE IF NOT EXISTS public.document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    document_id UUID NOT NULL,
    process_id UUID,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER,
    section_title TEXT,
    text_content TEXT NOT NULL,
    embedding JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    document_version TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT document_chunks_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT document_chunks_document_fkey
        FOREIGN KEY (document_id)
        REFERENCES public.discovered_documents (id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_document
    ON public.document_chunks (tenant_id, document_id, is_active);
CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant_active
    ON public.document_chunks (tenant_id, is_active);

COMMENT ON TABLE public.document_chunks IS
    'Agent 1 IR chunks. Hybrid BM25 + vector retrieval is tenant-scoped; Agent 1 never writes workflow stage.';

ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS document_chunks_service_role ON public.document_chunks;
DROP POLICY IF EXISTS document_chunks_tenant_authenticated ON public.document_chunks;

CREATE POLICY document_chunks_service_role ON public.document_chunks FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY document_chunks_tenant_authenticated ON public.document_chunks
    FOR SELECT TO authenticated
    USING (tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', ''));

DROP POLICY IF EXISTS discovered_documents_service_role ON public.discovered_documents;
DROP POLICY IF EXISTS discovered_documents_tenant_authenticated ON public.discovered_documents;
DROP POLICY IF EXISTS "anon_read_discovered_documents" ON public.discovered_documents;

CREATE POLICY discovered_documents_service_role ON public.discovered_documents FOR ALL TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY discovered_documents_tenant_authenticated ON public.discovered_documents
    FOR SELECT TO authenticated
    USING (
        tenant_id IS NULL
        OR tenant_id::text = coalesce(auth.jwt() -> 'app_metadata' ->> 'tenant_id', '')
    );
