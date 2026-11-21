from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=("../.env", ".env"),
        env_ignore_empty=True,
        extra="ignore",
    )

    # DATABASE_URL is shared with backend/ (Supabase session pooler); RAG_POSTGRES_DSN overrides it for rag/ only.
    postgres_dsn: str = Field(
        default="postgresql://rag@localhost:5432/rag",
        validation_alias=AliasChoices("RAG_POSTGRES_DSN", "DATABASE_URL"),
    )
    # Supabase free tier caps pooler connections and backend/ uses the same database.
    postgres_pool_max_size: int = 5
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "evidence_chunks"
    model_cache_dir: str = "/models"

    # Required for POST /ingest, DELETE /sources/{id} and POST /admin/eviction; empty = those endpoints are disabled.
    admin_token: str = ""

    dense_model: str = "BAAI/bge-m3"
    dense_dim: int = 1024
    sparse_model: str = "Qdrant/bm25"
    reranker_model: str = "BAAI/bge-reranker-v2-m3-int8"
    # Profile from app/languages/<code>.json (stemmer + stopwords) for BM25; FastEmbed has no Polish stemmer.
    corpus_language: str = "pl"

    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 200

    retrieval_limit_per_query: int = 30
    candidate_pool_size: int = 30
    rerank_top_k: int = 5
    # Qwen 3.5 9B loses recall in the middle of long prompts; more than 7 passages drowns the contradiction rules.
    rerank_top_k_max: int = 7
    # Sigmoid of the BGE reranker logit; below 0.5 (logit < 0) the pair is judged irrelevant, so it is not evidence.
    rerank_min_score: float = 0.5
    # Divides the logit before the sigmoid so strong matches (logit 5..10) stay distinguishable instead of all ~1.0.
    rerank_score_temperature: float = 4.0

    # Google Fact Check Tools API, queried live in /search; empty key = source disabled, corpus search still works.
    factcheck_api_key: str = Field(
        default="", validation_alias=AliasChoices("RAG_FACTCHECK_API_KEY", "FACTCHECK_API_KEY")
    )
    factcheck_url: str = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
    factcheck_language: str = "pl"
    factcheck_page_size: int = 10
    factcheck_max_reviews: int = 15
    # Kept well under rag's own 8 s budget in CONTRACT.md §2, so a slow Google never sinks the whole search.
    factcheck_timeout_seconds: float = 4.0
    # Same query within the TTL reuses the answer: fewer paid calls and the same result for repeated checks.
    factcheck_cache_ttl_seconds: int = 3600
    factcheck_cache_max_entries: int = 1000

    # Catalog of known disinformation campaigns (EUvsDisinfo, organizer's incident base), matched locally per search.
    incident_collection_name: str = "disinfo_incidents"
    incident_retrieval_limit: int = 10
    # Stricter than evidence: wrongly tying a claim to a hostile campaign does more harm than a weak citation.
    incident_min_score: float = 0.7
    incident_max_matches: int = 3
    incident_summary_max_chars: int = 400

    # Optional OpenAI-compatible endpoint (e.g. FastFlowLM) for query expansion; empty = rule-based only.
    expansion_llm_url: str = ""
    expansion_llm_model: str = "qwen3.5:9b"
    expansion_llm_api_key: str = ""
    expansion_llm_timeout_seconds: float = 20.0

    protection_days: int = 7
    eviction_max_active_chunks: int = 50000
    # Brief minimum for the demo corpus; eviction never shrinks the corpus below it.
    eviction_min_documents: int = 100
    eviction_min_domains: int = 10
    eviction_age_weight: float = 0.4
    eviction_read_weight: float = 0.6
    eviction_tier3_age_multiplier: float = 2.0
    eviction_topic_quota_share: float = 0.30
    eviction_topic_overquota_bonus: float = 30.0
    eviction_cron_hour: int = 3
    optimize_cron_hour: int = 4


settings = Settings()
