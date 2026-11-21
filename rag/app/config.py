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
        default="postgresql://rag:rag@localhost:5432/rag",
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
