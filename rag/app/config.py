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
    postgres_command_timeout_seconds: float = 5.0
    collection_name: str = "evidence_chunks"
    # Candidates the HNSW index inspects per query; higher is more accurate and slower (pgvector default is 40).
    hnsw_ef_search: int = 100
    # Writing a long document means hundreds of HNSW insertions, more than the ordinary command timeout allows.
    vector_write_timeout_seconds: float = 60.0
    model_cache_dir: str = "/models"

    # Required for POST /ingest, DELETE /sources/{id} and POST /admin/eviction; empty = those endpoints are disabled.
    admin_token: str = ""

    dense_model: str = "BAAI/bge-m3"
    dense_dim: int = 1024
    reranker_model: str = "BAAI/bge-reranker-v2-m3-int8"
    # Profile from app/languages/<code>.json (stemmer + stopwords) for BM25; FastEmbed has no Polish stemmer.
    corpus_language: str = "pl"

    # Cross-encoder cost grows with text length; 450-char chunks keep the ~12-candidate rerank in budget.
    chunk_max_chars: int = 450
    chunk_overlap_chars: int = 75
    # ONNX threads for embeddings and the reranker; 0 = all CPU cores.
    model_threads: int = 0

    retrieval_limit_per_query: int = 30
    # Rerank budget: 12 chunks x 450 chars + 10 fact-checks + 10 incident variants is about 5 s on CPU
    # (contract: rag max 12 s).
    candidate_pool_size: int = 12
    # One long page must not fill the rerank pool and starve independent evidence from other sources
    # (brief: the strength of a verdict comes from the number of independent confirmations).
    pool_max_chunks_per_document: int = 3
    rerank_top_k: int = 5
    # Small models (Qwen3 0.6B on FastFlowLM) lose recall in long prompts; more than 7 passages drowns the rules.
    rerank_top_k_max: int = 7
    # A new document is a copy when most of its chunks point to the same other document and the mean best cosine
    # is high. Measured on the demo corpus: re-fetched pages score mean 0.89-0.95 with share 0.75-1.0; distinct
    # pages of one site either keep the mean below 0.88 or spread their matches over many documents (share <= 0.67).
    near_duplicate_min_mean_cosine: float = 0.87
    near_duplicate_min_share: float = 0.7
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
    factcheck_max_reviews: int = 10
    # Kept well under rag's own 12 s budget in CONTRACT.md §2, so a slow Google never sinks the whole search.
    factcheck_timeout_seconds: float = 4.0
    # Same query within the TTL reuses the answer: fewer paid calls and the same result for repeated checks.
    factcheck_cache_ttl_seconds: int = 3600
    factcheck_cache_max_entries: int = 1000

    # Catalog of known disinformation campaigns (EUvsDisinfo, organizer's incident base), matched locally per search.
    incident_collection_name: str = "disinfo_incidents"
    incident_retrieval_limit: int = 5
    # Stricter than evidence: wrongly tying a claim to a hostile campaign does more harm than a weak citation.
    incident_min_score: float = 0.7
    incident_max_matches: int = 3
    incident_summary_max_chars: int = 400
    # app/data/seed_incidents.json fills an empty catalog at start (real EUvsDisinfo cases, context only).
    seed_incidents_enabled: bool = True

    # Team scraper writes pages into this table of the shared database (id, date YYYYMMDD, site, title, content).
    corpus_scraped_table: str = "ScrappedData"
    corpus_sync_max_documents: int = 5000
    # Dziennik Ustaw acts from the scraper (id, date YYYYMMDD, docid = Dz.U. position, doctitle, rule = one article).
    # POST /admin/corpus/law imports the acts listed in app/data/law_acts.json up to a text budget: embedding on CPU
    # costs about 8 min per 500k chars, so the default fits one coffee break and a rerun continues where it stopped.
    corpus_law_table: str = "Law"
    law_import_default_max_chars: int = 4_000_000
    law_import_max_chars: int = 50_000_000
    # Below DOCUMENT_MAX_CHARS of the ingest model; longer acts are split on article boundaries.
    law_part_max_chars: int = 450_000
    # Official sources are refreshed on a schedule (brief: timeliness, source maintenance): the seed pages are
    # fetched again every day and the Dz.U. acts re-imported once a week, so a newer consolidated text replaces
    # the old one. The same imports can still be started by hand through the admin endpoints.
    corpus_refresh_enabled: bool = True
    corpus_refresh_cron_hour: int = 5
    law_refresh_cron_day_of_week: str = "mon"
    law_refresh_cron_hour: int = 6
    law_refresh_max_chars: int = 4_000_000
    # A line present in at least this share of scraped pages is navigation boilerplate, not content.
    corpus_boilerplate_share: float = 0.3
    corpus_boilerplate_min_documents: int = 3
    # Public pages fetched by POST /admin/corpus/fetch; the client name is generic on purpose.
    corpus_fetch_max_urls: int = 100
    corpus_fetch_timeout_seconds: float = 15.0
    corpus_fetch_max_bytes: int = 2_000_000
    # Redirects are followed manually and every target is re-checked by the URL guard.
    corpus_fetch_max_redirects: int = 5
    corpus_fetch_max_bytes: int = 2_000_000
    corpus_fetch_delay_seconds: float = 0.5
    corpus_fetch_user_agent: str = "Prawdowid/0.1 (hackathon demo fact-checking corpus)"
    # POST /fetch for agent/: text returned for claim extraction, the page itself is not stored.
    fetch_max_text_chars: int = 20_000
    # Under agent/'s 12 s budget for the whole rag call; the corpus fetch below runs in the background.
    fetch_timeout_seconds: float = 10.0
    # Curated demo documents (app/data/seed_documents.json) fill facts the demo needs; missing ids are indexed at start.
    seed_corpus_enabled: bool = True

    # POST /ocr: text of a screenshot or photo read locally by Tesseract (no external image API, nothing stored).
    ocr_max_bytes: int = 5_000_000
    ocr_max_pixels: int = 25_000_000
    ocr_timeout_seconds: float = 15.0
    ocr_languages: str = "pol+eng"
    ocr_max_text_chars: int = 5000

    # EUvsDisinfo MCP server (Streamable HTTP, stateless mode); empty token = import disabled.
    euvsdisinfo_token: str = Field(
        default="", validation_alias=AliasChoices("RAG_EUVSDISINFO_TOKEN", "EUVSDISINFO_TOKEN")
    )
    euvsdisinfo_url: str = "https://mcp.euvsd.info/mcp"
    euvsdisinfo_page_size: int = 100
    euvsdisinfo_timeout_seconds: float = 60.0
    # Cases are newest first; CPU embedding of the full 19k+ register takes long, so syncs are bounded.
    euvsdisinfo_sync_default_cases: int = 1000
    euvsdisinfo_sync_max_cases: int = 25000
    euvsdisinfo_daily_sync_cases: int = 200
    euvsdisinfo_sync_cron_hour: int = 2

    # Gap filling from gov.pl: when the corpus has fewer relevant passages than gov_search_min_results, /search asks
    # the endpoint behind gov.pl/web/gov/szukaj (robots.txt allows all), indexes the best and the newest pages and
    # searches again. The whole fill stays under gov_search_budget_seconds, inside rag's 12 s (CONTRACT.md §2).
    gov_search_enabled: bool = True
    gov_search_url: str = "https://www.gov.pl/api/data/search"
    gov_search_site: str = "https://www.gov.pl"
    gov_search_candidates: int = 10
    gov_search_max_pages: int = 3
    gov_search_min_results: int = 1
    gov_search_timeout_seconds: float = 3.0
    gov_search_budget_seconds: float = 6.0
    # A stored gov.pl page older than this is downloaded again when a question needs it, so evidence stays current.
    gov_search_refresh_days: int = 30
    gov_search_cache_ttl_seconds: int = 3600
    gov_search_cache_max_entries: int = 1000

    # Same query + filters within the TTL and the same corpus version returns the cached response: identical
    # results across channels (brief scenario G) and no reranker cost on repeats. Memory only, keyed by hash.
    search_cache_ttl_seconds: int = 600
    search_cache_max_entries: int = 500

    # Optional OpenAI-compatible endpoint (e.g. hosted OpenAI or FastFlowLM) for query expansion; empty = rules only.
    expansion_llm_url: str = ""
    expansion_llm_model: str = "qwen3:0.6b"
    expansion_llm_api_key: str = ""
    # Sent only to api.openai.com, which rejects temperature on GPT-5/6 models; same defaults as agent/llm.go.
    expansion_llm_reasoning_effort: str = "none"
    expansion_llm_max_completion_tokens: int = 800
    # Must fit inside rag's 8 s budget together with retrieval and reranking; on timeout the rules take over.
    expansion_llm_timeout_seconds: float = 3.0
    # The same claim gets the same auxiliary queries even if the provider is not perfectly deterministic.
    # Entries hold the derived queries (they keep the claim's wording) and expire after the TTL.
    expansion_cache_ttl_seconds: int = 3600
    expansion_cache_max_entries: int = 500

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
    # Vector reconcile runs on the hour, the table vacuum half an hour later on a table without stale rows.
    optimize_cron_hour: int = 4
    optimize_cron_minute: int = 30


settings = Settings()
