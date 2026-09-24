import os
import pickle
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.decomposition import PCA
import logging

logger = logging.getLogger(__name__)

class LandscapeClusterEngine:
    def __init__(self, data_dir: str = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = data_dir or os.path.join(base_dir, "data")
        self.index_dir = os.path.join(self.data_dir, "index")
        
        # Paths to vectors and metadata
        self.index_bin_path = os.path.join(self.index_dir, "faiss_index.bin")
        self.metadata_path = os.path.join(self.index_dir, "index_metadata.pkl")
        
        self.metadata = None
        self.vectors = None
        
        # Models and results
        self.kmeans = None
        self.pca = None
        self.pca_coords = None
        self.cluster_labels = None
        self.silhouette = None
        
        self.functional_labels = {
            0: "Urban Core & Dense High-Density Built-Up",
            1: "Industrial, Bare Soil & Active Construction Corridors",
            2: "Permanent Water Bodies & Hooghly River Channel",
            3: "Dense Canopies, Wetlands & Mangrove Parks",
            4: "Agricultural Wetlands & Mixed Peri-Urban Landscape"
        }

    def _load_data(self):
        if not os.path.exists(self.metadata_path) or not os.path.exists(self.index_bin_path):
            raise FileNotFoundError("FAISS index or metadata not found. Please run index_manager.py to build the index.")
            
        with open(self.metadata_path, "rb") as f:
            # metadata in vector_index is just a list of tile_ids
            self.tile_ids = pickle.load(f)
            
        if not self.tile_ids:
            raise ValueError("Metadata is empty.")
            
        import faiss
        index = faiss.read_index(self.index_bin_path)
        self.vectors = np.array([index.reconstruct(i) for i in range(index.ntotal)], dtype=np.float32)
        
        # Normalize vectors as done in FAISS FlatIP
        norms = np.linalg.norm(self.vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1e-10
        self.vectors = self.vectors / norms

    def _assign_functional_labels(self):
        """
        Assigns functional labels based on spectral properties of the cluster centroids or members.
        Since we don't have raw spectral indices here natively, we will statically map cluster indices 
        to functional classes for this demonstration based on the implementation plan.
        Ideally we would compute mean NDVI/NDWI/Brightness per cluster, but we use the requested predefined mapping.
        """
        pass

    def compute_clusters(self, n_clusters=5):
        if self.vectors is None:
            self._load_data()
            
        if len(self.vectors) < n_clusters:
            raise ValueError(f"Not enough tiles ({len(self.vectors)}) to form {n_clusters} clusters.")
            
        logger.info(f"Computing {n_clusters}-Means on {len(self.vectors)} tiles...")
        
        # Compute K-Means
        self.kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
        self.cluster_labels = self.kmeans.fit_predict(self.vectors)
        
        # Compute Silhouette Score
        self.silhouette = float(silhouette_score(self.vectors, self.cluster_labels))
        logger.info(f"Silhouette Score: {self.silhouette:.4f}")
        
        # Compute 2D PCA for visualization
        self.pca = PCA(n_components=2, random_state=42)
        self.pca_coords = self.pca.fit_transform(self.vectors)
        
        self._assign_functional_labels()
        
        # Build cluster summaries
        cluster_counts = {int(k): int(v) for k, v in zip(*np.unique(self.cluster_labels, return_counts=True))}
        
        return {
            "silhouette_score": round(self.silhouette, 4),
            "cluster_counts": cluster_counts,
            "total_tiles": len(self.vectors)
        }

    def get_cluster_summary(self):
        if self.cluster_labels is None:
            self.compute_clusters()
            
        cluster_counts = {int(k): int(v) for k, v in zip(*np.unique(self.cluster_labels, return_counts=True))}
        summary = []
        for c_id in range(self.kmeans.n_clusters):
            summary.append({
                "cluster_id": c_id,
                "label": self.functional_labels.get(c_id, f"Cluster {c_id}"),
                "count": cluster_counts.get(c_id, 0),
                "percentage": round((cluster_counts.get(c_id, 0) / len(self.vectors)) * 100, 2)
            })
            
        return {
            "silhouette_score": self.silhouette,
            "clusters": summary
        }

    def get_tiles_in_cluster(self, cluster_id: int, max_tiles: int = 50):
        if self.cluster_labels is None:
            self.compute_clusters()
            
        indices = np.where(self.cluster_labels == cluster_id)[0]
        selected = indices[:max_tiles]
        
        results = []
        for idx in selected:
            # Convert pca_coords
            pca_x = float(self.pca_coords[idx, 0])
            pca_y = float(self.pca_coords[idx, 1])
            results.append({
                "tile_id": self.tile_ids[idx],
                "pca_x": pca_x,
                "pca_y": pca_y
            })
            
        return results

    def get_all_pca_data(self):
        """Returns PCA coordinates and cluster IDs for all tiles."""
        if self.pca_coords is None:
            self.compute_clusters()
            
        data = []
        for idx in range(len(self.vectors)):
            data.append({
                "tile_id": self.tile_ids[idx],
                "cluster_id": int(self.cluster_labels[idx]),
                "label": self.functional_labels.get(int(self.cluster_labels[idx]), f"Cluster {self.cluster_labels[idx]}"),
                "pca_x": float(self.pca_coords[idx, 0]),
                "pca_y": float(self.pca_coords[idx, 1]),
            })
        return data
