CREATE TABLE IF NOT EXISTS sources (
    document_id VARCHAR(255) PRIMARY KEY,
    title TEXT NOT NULL,
    publisher TEXT NOT NULL,
    url TEXT NOT NULL,
    published_at DATE,
    fetched_at DATE NOT NULL,
    license TEXT,
    source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('official', 'secondary', 'factcheck', 'incident'))
);

CREATE TABLE IF NOT EXISTS document_metadata (
    chunk_id UUID PRIMARY KEY,
    source_id VARCHAR(255) NOT NULL REFERENCES sources(document_id),
    topic_tag VARCHAR(100) NOT NULL,
    tier INT NOT NULL DEFAULT 2 CHECK (tier IN (1, 2, 3)),
    reliability VARCHAR(50) NOT NULL CHECK (reliability IN ('high', 'medium', 'low')),
    added_at TIMESTAMP NOT NULL DEFAULT NOW(),
    protected_until TIMESTAMP,
    read_count INT NOT NULL DEFAULT 0,
    last_accessed_at TIMESTAMP,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_document_metadata_active
    ON document_metadata (is_deleted, tier, protected_until);
