import os
from dataclasses import dataclass

from fastembed import SparseTextEmbedding, TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType
from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.config import settings
from app.languages import load_profile

BGE_M3_ONNX_FILE = "onnx/model.onnx"
BGE_M3_ONNX_WEIGHTS = "onnx/model.onnx_data"


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


class EmbeddingModels:
    """Dense (BGE-M3), sparse (BM25) and cross-encoder (BGE reranker) models, loaded once per process."""

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
        language = load_profile(settings.corpus_language)
        self._sparse = SparseTextEmbedding(
            settings.sparse_model,
            cache_dir=settings.model_cache_dir,
            stemmer=language.stemmer,
            stopwords=language.stopwords,
        )
        self._reranker = TextCrossEncoder(settings.reranker_model, cache_dir=settings.model_cache_dir, threads=threads)

    def embed_documents(self, texts: list[str]) -> tuple[list[list[float]], list[SparseVector]]:
        dense = [vector.tolist() for vector in self._dense.embed(texts)]
        sparse = [
            SparseVector(indices=vector.indices.tolist(), values=vector.values.tolist())
            for vector in self._sparse.embed(texts)
        ]
        return dense, sparse

    def embed_queries(self, queries: list[str]) -> tuple[list[list[float]], list[SparseVector]]:
        dense = [vector.tolist() for vector in self._dense.query_embed(queries)]
        sparse = [
            SparseVector(indices=vector.indices.tolist(), values=vector.values.tolist())
            for vector in self._sparse.query_embed(queries)
        ]
        return dense, sparse

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        return [float(score) for score in self._reranker.rerank(query, documents)]
