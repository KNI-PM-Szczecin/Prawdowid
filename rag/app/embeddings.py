import os

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType
from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.config import settings
from app.lexical import lexical_tokens

BGE_M3_ONNX_FILE = "onnx/model.onnx"
BGE_M3_ONNX_WEIGHTS = "onnx/model.onnx_data"


class EmbeddingModels:
    """Dense (BGE-M3) and cross-encoder (BGE reranker) models, loaded once per process."""

    def __init__(self) -> None:
        TextEmbedding.add_custom_model(
            model=settings.dense_model,
            pooling=PoolingType.CLS,
            normalization=True,
            sources=ModelSource(hf=settings.dense_model),
            dim=settings.dense_dim,
            model_file=BGE_M3_ONNX_FILE,
            additional_files=[BGE_M3_ONNX_WEIGHTS],
        )
        threads = settings.model_threads or os.cpu_count()
        self._dense = TextEmbedding(settings.dense_model, cache_dir=settings.model_cache_dir, threads=threads)
        self._reranker = TextCrossEncoder(settings.reranker_model, cache_dir=settings.model_cache_dir, threads=threads)

    def embed_documents(self, texts: list[str]) -> tuple[list[list[float]], list[list[str]]]:
        """Dense vectors plus the stemmed tokens that feed the lexical half of the hybrid search."""
        return [vector.tolist() for vector in self._dense.embed(texts)], [lexical_tokens(text) for text in texts]

    def embed_queries(self, queries: list[str]) -> tuple[list[list[float]], list[list[str]]]:
        return [vector.tolist() for vector in self._dense.query_embed(queries)], [
            lexical_tokens(query) for query in queries
        ]

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        return [float(score) for score in self._reranker.rerank(query, documents)]
