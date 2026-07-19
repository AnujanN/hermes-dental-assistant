import os
import re
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams

# Load env variables from local db_server/.env if exists
try:
    from dotenv import load_dotenv
    dotenv_path = Path(__file__).resolve().parent / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
except ImportError:
    pass

_encoder = None

def get_encoder():
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _encoder

_qdrant_client = None
_last_q_host = None

def get_qdrant_client():
    global _qdrant_client, _last_q_host
    q_host = os.environ.get("QDRANT_HOST", "db_data/qdrant_storage")
    
    if _qdrant_client is None or q_host != _last_q_host:
        q_port = int(os.environ.get("QDRANT_PORT", "6333"))
        q_api_key = os.environ.get("QDRANT_API_KEY", None)

        # Check if host points to a local directory or :memory:
        if q_host == ":memory:" or not q_host.startswith("http") and ("/" in q_host or "\\" in q_host or "storage" in q_host):
            if q_host != ":memory:":
                os.makedirs(q_host, exist_ok=True)
            _qdrant_client = QdrantClient(path=q_host)
        else:
            # Docker/Network or Qdrant Cloud connection
            if q_host.startswith("http://") or q_host.startswith("https://"):
                _qdrant_client = QdrantClient(url=q_host, api_key=q_api_key)
            else:
                _qdrant_client = QdrantClient(host=q_host, port=q_port, api_key=q_api_key)
        _last_q_host = q_host
        
    return _qdrant_client

def init_qdrant_collection(collection_name: str = "clinic_knowledge"):
    client = get_qdrant_client()
    vector_size = 384 
    
    collections = client.get_collections().collections
    exists = any(c.name == collection_name for c in collections)
    
    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        print(f"Qdrant collection '{collection_name}' successfully initialized.")
    else:
        print(f"Qdrant collection '{collection_name}' already exists.")

# --- Chunking & Ingestion ---

def chunk_markdown_file(file_path: str, chunk_size: int = 1000, overlap: int = 120):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source file not found at {file_path}")
        
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    sections = []
    current_header = "General info"
    current_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_lines:
                sections.append((current_header, "\n".join(current_lines).strip()))
                current_lines = []
            current_header = stripped.replace("#", "").strip()
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_header, "\n".join(current_lines).strip()))

    chunks = []
    for header, body in sections:
        if not body:
            continue
            
        if len(body) <= chunk_size:
            chunks.append({
                "content": f"Section: {header}\n\n{body}",
                "metadata": {"section": header}
            })
        else:
            start = 0
            while start < len(body):
                end = start + chunk_size
                if end < len(body):
                    nearest_period = body.rfind(". ", start, end)
                    if nearest_period != -1 and nearest_period > start + (chunk_size // 2):
                        end = nearest_period + 1
                
                chunk_text = body[start:end].strip()
                chunks.append({
                    "content": f"Section: {header} (cont.)\n\n{chunk_text}",
                    "metadata": {"section": header}
                })
                
                start += (chunk_size - overlap)
                
    return chunks

def ingest_knowledge_document(file_path: str, collection_name: str = "clinic_knowledge"):
    init_qdrant_collection(collection_name)
    
    chunks = chunk_markdown_file(file_path)
    if not chunks:
        print("No chunks generated from knowledge document.")
        return
        
    client = get_qdrant_client()
    encoder = get_encoder()
    
    points = []
    for idx, chunk in enumerate(chunks):
        text = chunk["content"]
        res = encoder.encode(text)
        vector = res.tolist() if hasattr(res, "tolist") else list(res)
        
        points.append(
            models.PointStruct(
                id=idx,
                vector=vector,
                payload={
                    "content": text,
                    "metadata": {
                        "source": os.path.basename(file_path),
                        "section": chunk["metadata"]["section"],
                        "chunk_id": idx
                    }
                }
            )
        )
        
    client.upsert(
        collection_name=collection_name,
        points=points
    )
    print(f"Successfully ingested {len(points)} chunks into Qdrant '{collection_name}'.")

# --- Retrieval ---

def search_knowledge(query: str, collection_name: str = "clinic_knowledge", top_k: int = 3, threshold: float = 0.70):
    client = get_qdrant_client()
    encoder = get_encoder()
    
    res = encoder.encode(query)
    query_vector = res.tolist() if hasattr(res, "tolist") else list(res)
    
    results = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=top_k,
        with_payload=True
    )
    
    hits = []
    for hit in results.points:
        if hit.score >= threshold:
            hits.append({
                "content": hit.payload["content"],
                "section": hit.payload["metadata"]["section"],
                "score": round(hit.score, 4)
            })
            
    return hits

if __name__ == "__main__":
    init_qdrant_collection()
    print("Qdrant collection setup verification complete.")
