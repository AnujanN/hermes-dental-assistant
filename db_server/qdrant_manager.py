import os
import re
import logging
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams

logger = logging.getLogger(__name__)

# Load env variables from local db_server/.env if exists
try:
    from dotenv import load_dotenv
    dotenv_path = Path(__file__).resolve().parent / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
except ImportError:
    pass

_encoder = None


class FastEmbedEncoder:
    def __init__(self):
        from fastembed import TextEmbedding
        self._model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

    def encode(self, text: str):
        return next(self._model.embed([text]))

def get_encoder():
    global _encoder
    if _encoder is None:
        _encoder = FastEmbedEncoder()
    return _encoder

_qdrant_client = None
_last_q_host = None


# ---------------------------------------------------------------------------
# Validation helpers (local to this module)
# ---------------------------------------------------------------------------

def _validate_file_path(file_path: str) -> str:
    """Validate that *file_path* is a non-empty string pointing to an existing file."""
    if not file_path or not str(file_path).strip():
        raise FileNotFoundError("File path is required and cannot be empty.")
    cleaned = str(file_path).strip()
    if not os.path.exists(cleaned):
        raise FileNotFoundError(f"Source file not found at {cleaned}")
    return cleaned


def _validate_collection_name(name: str) -> str:
    """Validate that *name* is a reasonable Qdrant collection name."""
    if not name or not str(name).strip():
        raise ValueError("Collection name is required and cannot be empty.")
    return str(name).strip()


def _validate_search_params(query: str, top_k: int, threshold: float) -> tuple:
    """Validate search parameters for Qdrant queries."""
    if not query or not str(query).strip():
        raise ValueError("Search query is required and cannot be empty.")
    cleaned_query = str(query).strip()

    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError(f"top_k must be a positive integer, got {top_k}.")
    if not isinstance(threshold, (int, float)) or not (0.0 <= threshold <= 1.0):
        raise ValueError(f"threshold must be between 0.0 and 1.0, got {threshold}.")

    return cleaned_query, top_k, threshold


# ---------------------------------------------------------------------------
# Qdrant client
# ---------------------------------------------------------------------------

def get_qdrant_client():
    global _qdrant_client, _last_q_host
    q_host = os.environ.get("QDRANT_HOST", "db_data/qdrant_storage")
    
    if _qdrant_client is None or q_host != _last_q_host:
        q_port = int(os.environ.get("QDRANT_PORT", "6333"))
        q_api_key = os.environ.get("QDRANT_API_KEY", None)
        logger.info("Connecting to Qdrant at host: '%s', port: %d", q_host, q_port)

        try:
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
            logger.info("QdrantClient connection established.")
        except Exception as exc:
            logger.error("Failed to connect to Qdrant at '%s': %s", q_host, exc, exc_info=True)
            raise
            
        _last_q_host = q_host
        
    return _qdrant_client

def init_qdrant_collection(collection_name: str = "clinic_knowledge"):
    """Create a Qdrant collection if it does not already exist."""
    collection_name = _validate_collection_name(collection_name)
    logger.info("Checking if Qdrant collection '%s' exists...", collection_name)
    client = get_qdrant_client()
    vector_size = 384 
    
    try:
        collections = client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)
        
        if not exists:
            logger.info("Creating Qdrant collection '%s' (vector size: %d)...", collection_name, vector_size)
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info("Qdrant collection '%s' successfully initialized.", collection_name)
        else:
            logger.info("Qdrant collection '%s' already exists.", collection_name)
    except Exception as exc:
        logger.error("Error during Qdrant collection check/creation for '%s': %s", collection_name, exc, exc_info=True)
        raise

# --- Chunking & Ingestion ---

def chunk_markdown_file(file_path: str, chunk_size: int = 1000, overlap: int = 120):
    """Parse a markdown file into overlapping text chunks grouped by heading."""
    file_path = _validate_file_path(file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        logger.error("Failed to read markdown file '%s': %s", file_path, exc)
        raise

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

    logger.info("Chunking markdown file '%s': Parsed %d sections.", file_path, len(sections))
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

def _encode_chunk(encoder, text: str, chunk_index: int) -> list:
    """Encode a single text chunk into a vector, with per-chunk error handling."""
    try:
        res = encoder.encode(text)
        return res.tolist() if hasattr(res, "tolist") else list(res)
    except Exception as exc:
        logger.error("Failed to encode chunk %d: %s", chunk_index, exc, exc_info=True)
        raise

def ingest_knowledge_document(file_path: str, collection_name: str = "clinic_knowledge"):
    """Chunk a markdown file, encode each chunk, and upsert vectors into Qdrant."""
    file_path = _validate_file_path(file_path)
    collection_name = _validate_collection_name(collection_name)

    logger.info("Starting ingestion of knowledge document: %s into collection: '%s'", file_path, collection_name)
    init_qdrant_collection(collection_name)
    
    try:
        chunks = chunk_markdown_file(file_path)
        if not chunks:
            logger.warning("No chunks generated from knowledge document '%s'. Ingestion skipped.", file_path)
            return
            
        client = get_qdrant_client()
        encoder = get_encoder()
        
        points = []
        for idx, chunk in enumerate(chunks):
            text = chunk["content"]
            vector = _encode_chunk(encoder, text, idx)
            
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
            
        logger.info("Upserting %d vector points into Qdrant...", len(points))
        client.upsert(
            collection_name=collection_name,
            points=points
        )
        logger.info("Successfully ingested %d chunks into Qdrant '%s'.", len(points), collection_name)
    except Exception as exc:
        logger.error("Ingestion failed for document %s: %s", file_path, exc, exc_info=True)
        raise

# --- Retrieval ---

def search_knowledge(query: str, collection_name: str = "clinic_knowledge", top_k: int = 3, threshold: float = 0.70):
    """Search the Qdrant collection for semantically matching chunks."""
    try:
        query, top_k, threshold = _validate_search_params(query, top_k, threshold)
    except ValueError as exc:
        logger.error("Invalid search parameters: %s", exc)
        return []

    collection_name = _validate_collection_name(collection_name)
    logger.info("Searching Qdrant '%s' for query: '%s' (top_k: %d, threshold: %.2f)", collection_name, query, top_k, threshold)
    client = get_qdrant_client()
    encoder = get_encoder()
    
    try:
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
                
        logger.info("Qdrant query finished. Found %d results, %d matched threshold.", len(results.points), len(hits))
        return hits
    except Exception as exc:
        logger.error("Qdrant search query failed for '%s': %s", query, exc, exc_info=True)
        return []

if __name__ == "__main__":
    init_qdrant_collection()
    print("Qdrant collection setup verification complete.")
