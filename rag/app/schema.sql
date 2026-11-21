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

CREATE INDEX IF NOT EXISTS idx_document_metadata_active
    ON document_metadata (is_deleted, tier, protected_until);
