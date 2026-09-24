import os
import json
import numpy as np
from database import tiles_collection, provenance_collection
from models import create_tile_document, create_provenance_document
from vector_index import VectorIndex
from embeddings import EmbeddingExtractor

def index_all_tiles(tiles_metadata_path: str, index_dir: str):
    if not os.path.exists(tiles_metadata_path):
        raise FileNotFoundError(f"Metadata file not found at {tiles_metadata_path}")

    with open(tiles_metadata_path, 'r') as f:
        tiles = json.load(f)

    print(f"Loaded {len(tiles)} tile metadata records. Initializing extractor...")
    v_index = VectorIndex(index_dir=index_dir)
    extractor = EmbeddingExtractor(local_files_only=True)

    indexed_count = 0
    for t in tiles:
        tile_id = t["tile_id"]
        filepath = t["filepath"]
        
        if not os.path.exists(filepath):
            print(f"Skipping missing tile: {filepath}")
            continue

        # Save metadata to MongoDB
        doc = create_tile_document(**t)
        tiles_collection.update_one(
            {"tile_id": tile_id},
            {"$set": doc},
            upsert=True
        )

        # Extract CLIP embedding
        vec = extractor.extract_from_tile(filepath)
        v_index.add_embedding(tile_id, vec)
        indexed_count += 1

    v_index.save()
    print(f"Successfully indexed {indexed_count} tiles into FAISS and MongoDB!")

    # Record provenance
    prov = create_provenance_document(
        action="batch_tile_indexing",
        source_files=[tiles_metadata_path],
        output_files=[v_index.index_path, v_index.metadata_path],
        parameters={"total_indexed": indexed_count, "embedding_dim": 512}
    )
    provenance_collection.insert_one(prov)

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(__file__))
    meta_path = os.path.join(base_dir, "data", "tiles", "tiles_metadata.json")
    idx_dir = os.path.join(base_dir, "data", "index")
    index_all_tiles(meta_path, idx_dir)
