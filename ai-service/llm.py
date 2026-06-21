"""Vertex AI chat/embeddings + pgvector 스토어 팩토리.

인증은 GCP ADC(application default credentials)로 한다 — API 키를 쓰지 않는다.
settings.GCP_PROJECT가 비어 있으면 호출이 실패하므로 .env에 반드시 설정한다.
"""
from functools import lru_cache

from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings
from langchain_postgres import PGVector

import settings


@lru_cache(maxsize=4)
def get_chat(temperature: float = 0.0) -> ChatVertexAI:
    """진단은 결정론적이어야 하므로 temperature 기본 0."""
    return ChatVertexAI(
        model=settings.CHAT_MODEL,
        temperature=temperature,
        project=settings.GCP_PROJECT or None,
        location=settings.GCP_LOCATION,
    )


@lru_cache(maxsize=1)
def get_embeddings() -> VertexAIEmbeddings:
    # dimensions: gemini-embedding-001의 MRL 출력 차원(settings.EMBEDDING_DIM).
    return VertexAIEmbeddings(
        model_name=settings.EMBEDDING_MODEL,
        project=settings.GCP_PROJECT or None,
        location=settings.GCP_LOCATION,
        dimensions=settings.EMBEDDING_DIM,
    )


def get_vector_store(collection_name: str) -> PGVector:
    """컬렉션별 PGVector 스토어. 코사인 거리 기본."""
    return PGVector(
        embeddings=get_embeddings(),
        connection=settings.DATABASE_URL,
        collection_name=collection_name,
        embedding_length=settings.EMBEDDING_DIM,
        use_jsonb=True,
    )


def cosine_distance_to_similarity(distance: float) -> float:
    """PGVector(cosine)가 돌려주는 거리(0=동일)를 유사도(1=동일, 0~1 클램프)로 변환."""
    sim = 1.0 - distance
    return max(0.0, min(1.0, sim))
