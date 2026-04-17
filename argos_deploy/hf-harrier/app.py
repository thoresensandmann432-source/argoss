from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Union
from transformers import pipeline
import torch
import numpy as np

# Load once at startup
pipe = pipeline(
    "feature-extraction",
    model="microsoft/harrier-oss-v1-0.6b",
    device=-1,
)

app = FastAPI(title="Harrier Feature Extraction", version="1.1")

class EmbedRequest(BaseModel):
    inputs: Union[str, List[str]]
    pool: str = "mean"  # mean | cls | none


def _pool_last_hidden(hidden, pool: str):
    # hidden: [seq_len, hidden_dim] or [batch, seq_len, hidden_dim]
    arr = np.array(hidden, dtype=np.float32)
    if arr.ndim == 2:  # single
        arr = arr[None, ...]
    if pool == "cls":
        return arr[:, 0, :]
    if pool == "none":
        return arr  # return token-level
    # default mean (excluding padding tokens is not possible with pipeline output), so simple mean
    return arr.mean(axis=1)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/embed")
def embed(req: EmbedRequest):
    try:
        outputs = pipe(req.inputs, truncation=True)
        pooled = _pool_last_hidden(outputs, req.pool)
        return {"embeddings": pooled.tolist(), "pooling": req.pool}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def root():
    return {
        "message": "POST /embed with {'inputs': 'text' | ['t1','t2'], 'pool': 'mean|cls|none'}",
        "default_pool": "mean"
    }
