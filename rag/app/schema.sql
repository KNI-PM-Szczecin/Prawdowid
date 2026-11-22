CREATE TABLE IF NOT EXISTS sources (
    document_id VARCHAR(255) PRIMARY KEY,
    title TEXT NOT NULL,
    publisher TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL,
    license TEXT,
    source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('official', 'secondary', 'factcheck', 'incident'))
);

CREATE TABLE IF NOT EXISTS document_metadata (
    chunk_id UUID PRIMARY KEY,
    source_id VARCHAR(255) NOT NULL REFERENCES sources(document_id),
    topic_tag VARCHAR(100) NOT NULL,
    tier INT NOT NULL DEFAULT 2 CHECK (tier IN (1, 2, 3)),
    reliability VARCHAR(50) NOT NULL CHECK (reliability IN ('high', 'medium', 'low')),
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    protected_until TIMESTAMPTZ,
    read_count INT NOT NULL DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- Supabase exposes the public schema through its REST API; RLS without policies blocks that path.
-- The table owner (our direct connection) bypasses RLS, so rag/ keeps full access.
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_metadata ENABLE ROW LEVEL SECURITY;

-- SHA-256 of the normalized text; two active documents with the same text are a poisoning or operator error.
ALTER TABLE sources ADD COLUMN IF NOT EXISTS content_hash CHAR(64);

-- Tables created by an earlier schema (DATE / TIMESTAMP columns) are migrated in place; no-op when already TIMESTAMPTZ.
ALTER TABLE sources ALTER COLUMN published_at TYPE TIMESTAMPTZ, ALTER COLUMN fetched_at TYPE TIMESTAMPTZ;
ALTER TABLE document_metadata
    ALTER COLUMN added_at TYPE TIMESTAMPTZ,
    ALTER COLUMN protected_until TYPE TIMESTAMPTZ,
    ALTER COLUMN last_accessed_at TYPE TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_document_metadata_active
    ON document_metadata (is_deleted, tier, protected_until);

-- Duplicate detection runs per ingested document; a full scan of sources would dominate bulk corpus syncs.
CREATE INDEX IF NOT EXISTS idx_sources_content_hash ON sources (content_hash);
