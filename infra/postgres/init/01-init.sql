-- KCpilot DB 초기화 스크립트.
-- pgvector/pgvector:pg16 이미지의 docker-entrypoint-initdb.d 훅으로
-- DB가 처음 생성될 때 한 번만 실행된다.

CREATE EXTENSION IF NOT EXISTS vector;
