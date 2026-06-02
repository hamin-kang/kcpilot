"""Gemini chat/embeddings + pgvector 스토어 팩토리.

GOOGLE_API_KEY는 load_dotenv()로 환경변수에 올라가 있어 두 클래스가 자동으로 읽는다.
"""
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector

import settings


@lru_cache(maxsize=4)
def get_chat(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    """진단은 결정론적이어야 하므로 temperature 기본 0."""
    return ChatGoogleGenerativeAI(
        model=settings.CHAT_MODEL,
        temperature=temperature,
        google_api_key=settings.GOOGLE_API_KEY or None,
    )


@lru_cache(maxsize=1)
def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        google_api_key=settings.GOOGLE_API_KEY or None,
        output_dimensionality=settings.EMBEDDING_DIM,
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
