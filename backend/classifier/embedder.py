"""
embedder.py

Local embedding engine for content-based file clustering.
Uses sentence-transformers for multilingual (Chinese + English) embeddings
and HDBSCAN/KMeans for automatic clustering.

This module eliminates the AI context window bottleneck by moving
content understanding to local computation.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_model = None


def _get_model():
    """Lazy-load the sentence-transformers model (cached after first call)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model '%s'…", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("Embedding model loaded.")
    return _model


def build_embedding_text(
    file_path: str,
    extraction: dict,
    max_content: int = 800,
) -> str:
    """
    Build the text representation for a single file, combining:
      - filename
      - parent/grandparent directory path
      - document title (if available from metadata)
      - content snippet (first max_content chars)

    This composite text captures multiple classification signals.
    """
    p = Path(file_path)
    name = p.name

    # Directory context
    parent = p.parent.name or ""
    gparent = p.parent.parent.name if len(p.parts) > 2 else ""
    dir_ctx = f"{gparent}/{parent}" if gparent else parent

    # Metadata
    meta = extraction.get("metadata", {}) if isinstance(extraction, dict) else {}
    title = (meta.get("title") or "").strip()

    # Content
    summary = (extraction.get("summary_text") or "")[:max_content]

    # Directory path is repeated to boost its weight in the embedding.
    # Same-directory files will naturally cluster closer together.
    parts = [name]
    if dir_ctx:
        parts.append(dir_ctx)
        parts.append(dir_ctx)  # repeat for stronger directory signal
    if title and title != name:
        parts.append(title)
    if summary:
        parts.append(summary)

    return " ".join(parts)


def embed_texts(texts: list[str], batch_size: int = 64) -> np.ndarray:
    """
    Generate embeddings for a list of texts.

    Returns an (N, D) numpy array where D is the embedding dimension (384).
    """
    model = _get_model()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,  # L2 normalised → cosine sim = dot product
    )
    return np.array(embeddings, dtype=np.float32)


def compute_centroids(
    embeddings: np.ndarray,
    groups: dict[str, list[int]],
) -> dict[str, np.ndarray]:
    """
    Compute centroid (mean embedding) for each group.

    Parameters
    ----------
    embeddings : (N, D) array — all file embeddings (0-based indexed)
    groups     : {group_name: [0-based indices]}

    Returns {group_name: (D,) centroid vector}
    """
    centroids = {}
    for name, indices in groups.items():
        if not indices:
            continue
        vecs = embeddings[indices]
        centroid = vecs.mean(axis=0)
        # Re-normalise
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid /= norm
        centroids[name] = centroid
    return centroids


def assign_to_nearest(
    file_embeddings: np.ndarray,
    centroids: dict[str, np.ndarray],
    threshold: float = 0.35,
) -> list[tuple[str, float]]:
    """
    Assign each file to the nearest centroid by cosine similarity.

    Parameters
    ----------
    file_embeddings : (M, D) array of file embeddings to assign
    centroids       : {name: (D,) centroid} from compute_centroids()
    threshold       : minimum similarity to accept assignment

    Returns list of (best_group_name, similarity) per file.
    If similarity < threshold, returns ("", similarity).
    """
    if not centroids:
        return [("", 0.0)] * len(file_embeddings)

    names = list(centroids.keys())
    centroid_matrix = np.stack([centroids[n] for n in names])  # (K, D)

    # Cosine similarity: since both are L2-normalised, dot product = cosine sim
    similarities = file_embeddings @ centroid_matrix.T  # (M, K)

    results = []
    for i in range(len(file_embeddings)):
        best_idx = int(np.argmax(similarities[i]))
        best_sim = float(similarities[i, best_idx])
        if best_sim >= threshold:
            results.append((names[best_idx], best_sim))
        else:
            results.append(("", best_sim))
    return results


def cluster_embeddings(
    embeddings: np.ndarray,
    min_cluster_size: int = 5,
    max_clusters: int = 8,
) -> dict[int, list[int]]:
    """
    Cluster embeddings using HDBSCAN with KMeans fallback.

    Parameters
    ----------
    embeddings       : (N, D) array
    min_cluster_size : minimum cluster size for HDBSCAN
    max_clusters     : maximum number of clusters

    Returns {cluster_id: [0-based indices]} — cluster_id=-1 means noise/outlier.
    """
    n = len(embeddings)
    if n < min_cluster_size * 2:
        # Too few files — put all in one cluster
        return {0: list(range(n))}

    try:
        from sklearn.cluster import HDBSCAN as _HDBSCAN
        clusterer = _HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=max(2, min_cluster_size // 2),
            metric="cosine",
        )
        labels = clusterer.fit_predict(embeddings)
    except Exception as e:
        logger.warning("HDBSCAN failed (%s), falling back to KMeans", e)
        from sklearn.cluster import KMeans
        k = min(max_clusters, max(2, n // min_cluster_size))
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(embeddings)

    clusters: dict[int, list[int]] = {}
    for i, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(i)

    # Limit cluster count: merge smallest clusters into noise
    real_clusters = {k: v for k, v in clusters.items() if k != -1}
    if len(real_clusters) > max_clusters:
        sorted_clusters = sorted(real_clusters.items(), key=lambda x: -len(x[1]))
        kept = dict(sorted_clusters[:max_clusters])
        noise = clusters.get(-1, [])
        for k, v in sorted_clusters[max_clusters:]:
            noise.extend(v)
        clusters = kept
        if noise:
            clusters[-1] = noise

    return clusters


def get_representative_indices(
    embeddings: np.ndarray,
    cluster_indices: list[int],
    n_representatives: int = 5,
) -> list[int]:
    """
    Select representative files from a cluster — those closest to the centroid.

    Returns up to n_representatives 0-based indices from cluster_indices.
    """
    if len(cluster_indices) <= n_representatives:
        return cluster_indices

    vecs = embeddings[cluster_indices]
    centroid = vecs.mean(axis=0)
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid /= norm

    # Cosine similarity to centroid
    sims = vecs @ centroid
    top_local = np.argsort(sims)[-n_representatives:][::-1]
    return [cluster_indices[i] for i in top_local]
