import faiss
import numpy as np
import os
import pickle

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

        self.load()

    def add_embedding(self, tile_id: str, embedding: np.ndarray):
        """
        Adds a single embedding to the index.
        embedding shape should be (dimension,)
        """
        if embedding.shape[0] != self.dimension:
            raise ValueError(f"Embedding dimension {embedding.shape[0]} does not match index dimension {self.dimension}")
        
        # faiss expects shape (n, d)
        vec = np.expand_dims(embedding, axis=0)
        self.index.add(vec)
        self.tile_ids.append(tile_id)

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

    def save(self):
        faiss.write_index(self.index, self.index_path)
        with open(self.metadata_path, 'wb') as f:
            pickle.dump(self.tile_ids, f)

    def load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.metadata_path, 'rb') as f:
                self.tile_ids = pickle.load(f)
