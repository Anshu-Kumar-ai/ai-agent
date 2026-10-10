"""Vector storage and RAG module for Stage 16 - Advanced Memory.

Provides:
- FAISS-based vector storage
- Document chunking
- Text embedding (using sentence-transformers or fallback)
- RAG tool for retrieval-augmented generation
- Persistence to disk
"""

import hashlib
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

from app.tools.base import BaseTool


@dataclass
class Document:
    """A document chunk with metadata."""
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: np.ndarray | None = None


@dataclass
class SearchResult:
    """Result from vector search."""
    document: Document
    score: float
    distance: float


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """Generate embeddings for a list of texts."""

    @abstractmethod
    def embed_single(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""


class SentenceTransformerEmbedding(EmbeddingProvider):
    """Embedding using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise RuntimeError("sentence-transformers not available. Install with: pip install sentence-transformers")
        self.model = SentenceTransformer(model_name)
        self._dimension = self.model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

    def embed_single(self, text: str) -> np.ndarray:
        return self.model.encode([text], convert_to_numpy=True, normalize_embeddings=True)[0]

    @property
    def dimension(self) -> int:
        return self._dimension


class HashEmbedding(EmbeddingProvider):
    """Fallback embedding using deterministic hashing (for testing/offline)."""

    def __init__(self, dimension: int = 384):
        self._dimension = dimension

    def _text_to_vector(self, text: str) -> np.ndarray:
        """Convert text to deterministic vector using hashing."""
        # Use multiple hash functions for better distribution
        vec = np.zeros(self._dimension, dtype=np.float32)
        words = text.lower().split()
        for i, word in enumerate(words):
            # Hash the word and use as seed
            h = hash(word) % (2**32)
            np.random.seed(h)
            vec += np.random.randn(self._dimension).astype(np.float32)
        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = [self._text_to_vector(t) for t in texts]
        return np.array(vectors, dtype=np.float32)

    def embed_single(self, text: str) -> np.ndarray:
        return self._text_to_vector(text)

    @property
    def dimension(self) -> int:
        return self._dimension


class VectorStore:
    """FAISS-based vector store for document storage and retrieval."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        index_path: str | None = None,
        metadata_path: str | None = None
    ):
        if not FAISS_AVAILABLE:
            raise RuntimeError("FAISS not available. Install with: pip install faiss-cpu")

        self.embedding_provider = embedding_provider
        self.dimension = embedding_provider.dimension

        # FAISS index (using Inner Product for cosine similarity with normalized vectors)
        self.index = faiss.IndexFlatIP(self.dimension)

        # Document storage
        self.documents: dict[str, Document] = {}
        self.id_to_index: dict[str, int] = {}  # doc_id -> index in FAISS
        self.index_to_id: dict[int, str] = {}  # FAISS index -> doc_id

        # Persistence paths
        self.index_path = index_path or os.path.join(os.getenv("HERMES_WORKSPACE", os.getcwd()), "data", "vector_index.faiss")
        self.metadata_path = metadata_path or os.path.join(os.getenv("HERMES_WORKSPACE", os.getcwd()), "data", "vector_metadata.json")

        # Load existing data if available
        self._load()

    def add_documents(self, documents: list[Document]) -> list[str]:
        """Add documents to the vector store."""
        if not documents:
            return []

        # Generate embeddings for new documents
        texts = [doc.text for doc in documents]
        embeddings = self.embedding_provider.embed(texts)

        # Add to FAISS index
        start_idx = self.index.ntotal
        self.index.add(embeddings.astype(np.float32))

        # Store documents
        doc_ids = []
        for i, doc in enumerate(documents):
            doc.embedding = embeddings[i]
            if not doc.id:
                doc.id = hashlib.sha256(doc.text.encode()).hexdigest()[:16]

            faiss_idx = start_idx + i
            self.documents[doc.id] = doc
            self.id_to_index[doc.id] = faiss_idx
            self.index_to_id[faiss_idx] = doc.id
            doc_ids.append(doc.id)

        return doc_ids

    def search(self, query: str, k: int = 5, threshold: float = 0.0) -> list[SearchResult]:
        """Search for similar documents."""
        if self.index.ntotal == 0:
            return []

        query_embedding = self.embedding_provider.embed_single(query)
        query_embedding = query_embedding.reshape(1, -1).astype(np.float32)

        # Search
        k = min(k, self.index.ntotal)
        scores, indices = self.index.search(query_embedding, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            if score < threshold:
                continue
            doc_id = self.index_to_id.get(idx)
            if doc_id and doc_id in self.documents:
                doc = self.documents[doc_id]
                results.append(SearchResult(
                    document=doc,
                    score=float(score),
                    distance=float(1 - score)  # Cosine distance
                ))

        return results

    def get_document(self, doc_id: str) -> Document | None:
        """Get a document by ID."""
        return self.documents.get(doc_id)

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document (mark as deleted - FAISS doesn't support true deletion)."""
        if doc_id in self.documents:
            del self.documents[doc_id]
            # Note: FAISS doesn't support true deletion, we just remove from our mapping
            if doc_id in self.id_to_index:
                idx = self.id_to_index.pop(doc_id)
                self.index_to_id.pop(idx, None)
            return True
        return False

    def clear(self) -> None:
        """Clear all documents."""
        self.index.reset()
        self.documents.clear()
        self.id_to_index.clear()
        self.index_to_id.clear()

    def save(self) -> None:
        """Save index and metadata to disk."""
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)

        # Save FAISS index
        faiss.write_index(self.index, self.index_path)

        # Save metadata
        metadata = {
            "documents": {},
            "id_to_index": self.id_to_index,
            "index_to_id": {str(k): v for k, v in self.index_to_id.items()},
            "dimension": self.dimension,
        }
        for doc_id, doc in self.documents.items():
            metadata["documents"][doc_id] = {
                "id": doc.id,
                "text": doc.text,
                "metadata": doc.metadata,
            }

        with open(self.metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def _load(self) -> None:
        """Load index and metadata from disk."""
        if not os.path.exists(self.index_path) or not os.path.exists(self.metadata_path):
            return

        try:
            # Load FAISS index
            self.index = faiss.read_index(self.index_path)

            # Load metadata
            with open(self.metadata_path) as f:
                metadata = json.load(f)

            self.id_to_index = metadata.get("id_to_index", {})
            self.index_to_id = {int(k): v for k, v in metadata.get("index_to_id", {}).items()}

            # Load documents
            for doc_id, doc_data in metadata.get("documents", {}).items():
                doc = Document(
                    id=doc_data["id"],
                    text=doc_data["text"],
                    metadata=doc_data["metadata"],
                )
                self.documents[doc_id] = doc

        except Exception as e:
            print(f"[VectorStore] Could not load existing data: {e}")
            # Start fresh
            self.index = faiss.IndexFlatIP(self.dimension)
            self.documents.clear()
            self.id_to_index.clear()
            self.index_to_id.clear()


class DocumentChunker:
    """Split documents into chunks for embedding."""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: list[str] | None = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", "! ", "? ", ", ", " ", ""]

    def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[Document]:
        """Split text into overlapping chunks."""
        if not text.strip():
            return []

        chunks = self._split_text(text)
        documents = []

        base_metadata = metadata or {}
        for i, chunk_text in enumerate(chunks):
            doc_metadata = base_metadata.copy()
            doc_metadata["chunk_index"] = i
            doc_metadata["chunk_count"] = len(chunks)

            doc = Document(
                id=hashlib.sha256(f"{text}:{i}".encode()).hexdigest()[:16],
                text=chunk_text.strip(),
                metadata=doc_metadata,
            )
            documents.append(doc)

        return documents

    def _split_text(self, text: str) -> list[str]:
        """Split text using separators with overlap."""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            if end >= len(text):
                chunks.append(text[start:])
                break

            # Try to find a separator near the end
            best_sep_pos = -1
            for sep in self.separators:
                pos = text.rfind(sep, start, end)
                if pos != -1:
                    best_sep_pos = pos + len(sep)
                    break

            if best_sep_pos > start:
                end = best_sep_pos

            chunks.append(text[start:end])
            start = end - self.chunk_overlap
            if start < 0:
                start = 0

        return chunks


class RAGTool(BaseTool):
    """Retrieval-Augmented Generation tool."""

    name = "rag.query"
    description = "Query the knowledge base using retrieval-augmented generation"
    selection_phrases = ("ask about", "search knowledge", "look up", "find in docs", "rag", "retrieve")
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Query to search the knowledge base",
            },
            "k": {
                "type": "integer",
                "description": "Number of results to retrieve",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
            "threshold": {
                "type": "number",
                "description": "Minimum similarity threshold (0-1)",
                "default": 0.3,
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "collection": {
                "type": "string",
                "description": "Knowledge collection to search (default: default)",
                "default": "default",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def validate_arguments(self, arguments: dict) -> None:
        if "query" not in arguments:
            raise ValueError("Missing required argument: 'query'")
        query = arguments["query"]
        if not isinstance(query, str) or not query.strip():
            raise ValueError("'query' must be a non-empty string")

        k = arguments.get("k", 5)
        if not isinstance(k, int) or k < 1 or k > 20:
            raise ValueError("'k' must be an integer between 1 and 20")

        threshold = arguments.get("threshold", 0.3)
        if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
            raise ValueError("'threshold' must be a number between 0 and 1")

    def execute(self, **kwargs) -> dict[str, Any]:
        query = kwargs["query"]
        k = kwargs.get("k", 5)
        threshold = kwargs.get("threshold", 0.3)
        collection = kwargs.get("collection", "default")

        try:
            results = self.vector_store.search(query, k=k, threshold=threshold)

            if not results:
                return {
                    "query": query,
                    "results": [],
                    "answer": "No relevant documents found in the knowledge base.",
                    "sources": [],
                }

            # Build context from retrieved documents
            context_parts = []
            sources = []

            for i, result in enumerate(results):
                doc = result.document
                context_parts.append(f"[Source {i+1}] {doc.text}")
                sources.append({
                    "id": doc.id,
                    "text_preview": doc.text[:200] + ("..." if len(doc.text) > 200 else ""),
                    "metadata": doc.metadata,
                    "score": result.score,
                    "distance": result.distance,
                })

            context = "\n\n".join(context_parts)

            return {
                "query": query,
                "results": len(results),
                "context": context,
                "sources": sources,
            }

        except Exception as e:
            return {
                "query": query,
                "error": f"RAG query failed: {type(e).__name__}: {e}",
                "results": [],
                "answer": "",
                "sources": [],
            }


class DocumentAddTool(BaseTool):
    """Add documents to the knowledge base."""

    name = "rag.add"
    description = "Add documents to the knowledge base for RAG"
    selection_phrases = ("add to knowledge", "store document", "save to knowledge base", "index document")
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text content to add",
            },
            "metadata": {
                "type": "object",
                "description": "Optional metadata for the document",
                "additionalProperties": True,
                "default": {},
            },
            "chunk": {
                "type": "boolean",
                "description": "Whether to chunk the text (default: true)",
                "default": True,
            },
            "collection": {
                "type": "string",
                "description": "Knowledge collection (default: default)",
                "default": "default",
            },
        },
        "required": ["text"],
        "additionalProperties": False,
    }

    def __init__(self, vector_store: VectorStore, chunker: DocumentChunker):
        self.vector_store = vector_store
        self.chunker = chunker

    def validate_arguments(self, arguments: dict) -> None:
        if "text" not in arguments:
            raise ValueError("Missing required argument: 'text'")
        text = arguments["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("'text' must be a non-empty string")

    def execute(self, **kwargs) -> dict[str, Any]:
        text = kwargs["text"]
        metadata = kwargs.get("metadata", {})
        chunk = kwargs.get("chunk", True)
        collection = kwargs.get("collection", "default")

        try:
            if chunk:
                documents = self.chunker.chunk(text, metadata)
            else:
                doc = Document(
                    id=hashlib.sha256(text.encode()).hexdigest()[:16],
                    text=text,
                    metadata=metadata,
                )
                documents = [doc]

            doc_ids = self.vector_store.add_documents(documents)
            self.vector_store.save()

            return {
                "added": len(documents),
                "document_ids": doc_ids,
                "collection": collection,
            }

        except Exception as e:
            return {
                "error": f"Failed to add document: {type(e).__name__}: {e}",
                "added": 0,
                "document_ids": [],
            }


class KnowledgeStatsTool(BaseTool):
    """Get statistics about the knowledge base."""

    name = "rag.stats"
    description = "Get statistics about the knowledge base"
    selection_phrases = ("knowledge stats", "rag stats", "knowledge base size", "how many documents")
    parameters = {
        "type": "object",
        "properties": {
            "collection": {
                "type": "string",
                "description": "Knowledge collection (default: default)",
                "default": "default",
            },
        },
        "required": [],
        "additionalProperties": False,
    }

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    def execute(self, **kwargs) -> dict[str, Any]:
        collection = kwargs.get("collection", "default")

        try:
            total_docs = len(self.vector_store.documents)
            total_chars = sum(len(doc.text) for doc in self.vector_store.documents.values())
            index_size = self.vector_store.index.ntotal

            return {
                "collection": collection,
                "total_documents": total_docs,
                "total_characters": total_chars,
                "index_size": index_size,
                "embedding_dimension": self.vector_store.dimension,
            }
        except Exception as e:
            return {
                "error": f"Failed to get stats: {type(e).__name__}: {e}",
            }


def create_rag_tools(
    embedding_provider: EmbeddingProvider | None = None,
    chunker: DocumentChunker | None = None,
    vector_store_path: str | None = None
) -> list[BaseTool]:
    """Create all RAG tools."""

    # Default embedding provider
    if embedding_provider is None:
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            embedding_provider = SentenceTransformerEmbedding()
        else:
            embedding_provider = HashEmbedding()

    # Default chunker
    if chunker is None:
        chunker = DocumentChunker()

    # Vector store
    vector_store = VectorStore(embedding_provider, index_path=vector_store_path)

    return [
        RAGTool(vector_store),
        DocumentAddTool(vector_store, chunker),
        KnowledgeStatsTool(vector_store),
    ]
