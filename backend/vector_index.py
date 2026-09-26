import faiss
import numpy as np
import os
import pickle
import json

class VectorIndex:
    def __init__(self, index_dir: str, dimension: int = 512):
        self.index_dir = index_dir
        os.makedirs(self.index_dir, exist_ok=True)
        self.index_path = os.path.join(self.index_dir, "faiss_index.bin")
        self.metadata_path = os.path.join(self.index_dir, "index_metadata.pkl")
        self.dimension = dimension
        
        # We will use Inner Product (which is Cosine Similarity if vectors are normalized)
        self.index = faiss.IndexFlatIP(self.dimension)
        self.tile_ids = [] # map internal faiss index to our tile_ids

        self.manifest_path = os.path.join(self.index_dir, "index_manifest.json")
        self.incremental_additions_count = 0
        self.load()

    def add_embedding(self, tile_id: str, embedding: np.ndarray):
        """
        Adds a single embedding to the index incrementally.
        embedding shape should be (dimension,)
        """
        if embedding.shape[0] != self.dimension:
            raise ValueError(f"Embedding dimension {embedding.shape[0]} does not match index dimension {self.dimension}")
        
        # faiss expects shape (n, d)
        vec = np.expand_dims(embedding, axis=0)
        self.index.add(vec)
        self.tile_ids.append(tile_id)
        self.incremental_additions_count += 1

    def search(self, query_embedding: np.ndarray, top_k: int = 5):
        """
        Searches the index for the most similar embeddings.
        query_embedding shape should be (dimension,)
        """
        if self.index.ntotal == 0:
            return []

        vec = np.expand_dims(query_embedding, axis=0)
        distances, indices = self.index.search(vec, top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1: # faiss returns -1 if there are not enough results
                results.append({
                    "tile_id": self.tile_ids[idx],
                    "score": float(distances[0][i])
                })
        return results

    def verify_consistency(self, catalog_count: int = None) -> dict:
        """
        Verifies FAISS vector count against metadata records for index consistency.
        """
        faiss_cnt = self.index.ntotal
        meta_cnt = len(self.tile_ids)
        
        consistent = (faiss_cnt == meta_cnt)
        if catalog_count is not None and consistent:
            consistent = (faiss_cnt == catalog_count)

        if consistent:
            status = "INDEX CONSISTENT"
            msg = f"FAISS vector count ({faiss_cnt}) perfectly matches indexed metadata records."
        else:
            status = "INDEX CONSISTENCY WARNING"
            msg = f"FAISS vector count ({faiss_cnt}) mismatches metadata records (meta: {meta_cnt}, catalog: {catalog_count})."

        return {
            "is_consistent": consistent,
            "status_code": status,
            "faiss_vector_count": faiss_cnt,
            "metadata_tile_count": meta_cnt,
            "catalog_count": catalog_count,
            "status_message": msg
        }

    def update_manifest(self) -> dict:
        """
        Updates and persists index manifest with 9 metadata fields.
        """
        import hashlib
        from datetime import datetime, timezone
        
        index_hash = "N/A"
        if os.path.exists(self.index_path):
            hasher = hashlib.sha256()
            with open(self.index_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            index_hash = hasher.hexdigest()

        now_iso = datetime.now(timezone.utc).isoformat()
        
        existing_manifest = {}
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as mf:
                    existing_manifest = json.load(mf)
            except Exception:
                pass

        build_time = existing_manifest.get("build_timestamp", now_iso)
        add_cnt = existing_manifest.get("incremental_additions_count", 0) + self.incremental_additions_count
        self.incremental_additions_count = 0

        manifest = {
            "index_type": "FAISS IndexFlatIP (Inner Product)",
            "embedding_model": "OpenAI CLIP ViT-B/32",
            "embedding_dimension": self.dimension,
            "vector_count": self.index.ntotal,
            "build_timestamp": build_time,
            "last_incremental_update": now_iso,
            "incremental_additions_count": add_cnt,
            "source_imagery_count": len(self.tile_ids),
            "index_file_sha256": index_hash
        }

        try:
            with open(self.manifest_path, "w", encoding="utf-8") as mf:
                json.dump(manifest, mf, indent=2)
        except Exception as e:
            print(f"Warning: Could not save index_manifest.json: {e}")

        return manifest

    def save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, 'wb') as f:
            pickle.dump(self.tile_ids, f)
        self.update_manifest()

    def load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.metadata_path, 'rb') as f:
                self.tile_ids = pickle.load(f)
            self.update_manifest()

