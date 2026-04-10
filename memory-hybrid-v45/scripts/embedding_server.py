#!/usr/bin/env python3
"""
Local embedding server compatible with OpenAI /v1/embeddings API.
Uses sentence-transformers with BAAI/bge-small-zh-v1.5 (512 dims).
"""

import os
import sys
import time
import logging

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Union
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Model config from environment
MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
HF_HOME = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
HOST = os.environ.get("EMBEDDING_HOST", "127.0.0.1")
PORT = int(os.environ.get("EMBEDDING_PORT", "8090"))

os.environ["HF_HOME"] = HF_HOME
os.environ["TRANSFORMERS_CACHE"] = os.path.join(HF_HOME, "hub")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

app = FastAPI(title="Embedding Server")
model = None


def load_model():
    global model
    from sentence_transformers import SentenceTransformer
    logger.info(f"Loading model {MODEL_NAME} (HF_HOME={HF_HOME})...")
    start = time.time()
    model = SentenceTransformer(MODEL_NAME, cache_folder=os.path.join(HF_HOME, "hub"))
    logger.info(f"Model loaded in {time.time() - start:.1f}s, dim={model.get_sentence_embedding_dimension()}")


class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]]
    model: str = MODEL_NAME


class EmbeddingData(BaseModel):
    object: str = "embedding"
    embedding: List[float]
    index: int = 0


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str = MODEL_NAME
    usage: dict = {"prompt_tokens": 0, "total_tokens": 0}


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "ready": model is not None}


@app.post("/v1/embeddings")
def create_embedding(req: EmbeddingRequest):
    if model is None:
        load_model()

    texts = [req.input] if isinstance(req.input, str) else req.input
    embeddings = model.encode(texts, normalize_embeddings=True)

    data = []
    for i, emb in enumerate(embeddings):
        data.append(EmbeddingData(embedding=emb.tolist(), index=i))

    return EmbeddingResponse(data=data, model=req.model)


if __name__ == "__main__":
    # Eagerly load model on startup
    load_model()
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
