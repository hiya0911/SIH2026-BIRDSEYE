import os
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window
from preprocessing import Preprocessor
import uuid
import json

class Tiler:
    def __init__(self, data_dir: str, tile_size: int = 256, valid_threshold: float = 0.5):
        self.data_dir = data_dir
        self.tile_size = tile_size
        self.valid_threshold = valid_threshold
        self.tiles_dir = os.path.join(os.path.dirname(data_dir), "data", "tiles")
        os.makedirs(self.tiles_dir, exist_ok=True)
        self.preprocessor = Preprocessor(data_dir)

    def generate_tiles(self, max_tiles: int = None):
        """
        Iterates over the 10m raster, extracts tile_size x tile_size windows,
        checks the valid pixel percentage based on SCL, and saves valid tiles.
        Returns a list of tile metadata dictionaries.
        """
        band_names = ["B02", "B03", "B04", "B08"]
        band_files = [self.preprocessor._find_band_file(b, "10m") for b in band_names]
        scl_file = self.preprocessor._find_band_file("SCL", "20m")

        if any(f is None for f in band_files) or scl_file is None:
            raise FileNotFoundError("One or more required band files could not be located.")

        # Open datasets once
        band_srcs = [rasterio.open(f) for f in band_files]
        scl_src = rasterio.open(scl_file)

        base_meta = band_srcs[0].meta.copy()
        width = band_srcs[0].width
        height = band_srcs[0].height

        from preprocessing import VALID_SCL_VALUES
        import numpy as np

        tiles_metadata = []

        try:
            for row_off in range(0, height, self.tile_size):
                for col_off in range(0, width, self.tile_size):
                    w = min(self.tile_size, width - col_off)
                    h = min(self.tile_size, height - row_off)
                    
                    if w < self.tile_size or h < self.tile_size:
                        continue

                    window = Window(col_off, row_off, w, h)
                    
                    # Read SCL window and resample
                    scl_window = Window(col_off // 2, row_off // 2, w // 2, h // 2)
                    scl_data = scl_src.read(1, window=scl_window, out_shape=(h, w), resampling=Resampling.nearest)
                    mask = np.isin(scl_data, VALID_SCL_VALUES)

                    valid_ratio = float(mask.sum() / (w * h))
                    if valid_ratio < self.valid_threshold:
                        continue

                    # Read 10m bands
                    bands_data = np.stack([src.read(1, window=window) for src in band_srcs], axis=0)

                    tile_id = str(uuid.uuid4())
                    tile_filename = f"tile_{tile_id}.tif"
                    tile_path = os.path.join(self.tiles_dir, tile_filename)

                    meta = base_meta.copy()
                    meta.update({
                        "driver": "GTiff",
                        "count": bands_data.shape[0],
                        "height": h,
                        "width": w,
                        "transform": rasterio.windows.transform(window, base_meta["transform"]),
                        "nodata": 0
                    })

                    masked_data = bands_data * mask

                    with rasterio.open(tile_path, "w", **meta) as dest:
                        dest.write(masked_data)

                    bounds = rasterio.windows.bounds(window, base_meta["transform"])
                    
                    tile_info = {
                        "tile_id": tile_id,
                        "filename": tile_filename,
                        "filepath": tile_path,
                        "bbox": list(bounds),
                        "crs": meta["crs"].to_string(),
                        "valid_ratio": round(valid_ratio, 4),
                        "resolution": base_meta["transform"][0],
                        "acquisition_datetime": "2024-02-23T04:38:09.024Z",
                        "source_scene": "L2A_T45QXF_A036381_20240223T044642"
                    }
                    tiles_metadata.append(tile_info)

                    if max_tiles and len(tiles_metadata) >= max_tiles:
                        break
                if max_tiles and len(tiles_metadata) >= max_tiles:
                    break
        finally:
            for s in band_srcs:
                s.close()
            scl_src.close()

        metadata_path = os.path.join(self.tiles_dir, "tiles_metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(tiles_metadata, f, indent=2)

        return tiles_metadata

