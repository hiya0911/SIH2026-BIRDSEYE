import os
import rasterio
import numpy as np
from rasterio.windows import Window, from_bounds
from rasterio.enums import Resampling
from scipy.ndimage import median_filter
from PIL import Image

VALID_SCL_VALUES = [4, 5, 6, 7, 11, 2]

class TemporalChangeEngine:
    def __init__(self, data_dir: str = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = data_dir or os.path.join(base_dir, "data")
        
        if not os.path.exists(self.data_dir):
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")

        # Scan for all available SAFE folders and index by year
        self.epochs = {}
        self._scan_epochs()

    def _scan_epochs(self):
        """
        Scans data_dir for Sentinel-2 SAFE packages and indexes them by year.
        """
        for item in os.listdir(self.data_dir):
            item_path = os.path.join(self.data_dir, item)
            if os.path.isdir(item_path) and item.endswith(".SAFE"):
                # Extract year from filename (e.g. S2B_MSIL2A_20240223... -> 2024)
                parts = item.split("_")
                year = None
                date_str = None
                for p in parts:
                    if len(p) >= 8 and p[:4].isdigit() and p[4:6].isdigit() and p[6:8].isdigit():
                        year = int(p[:4])
                        date_str = f"{p[:4]}-{p[4:6]}-{p[6:8]}"
                        break
                
                granule_dir = os.path.join(item_path, "GRANULE")
                if os.path.exists(granule_dir):
                    for g in os.listdir(granule_dir):
                        if g.startswith("L2A_"):
                            granule_path = os.path.join(granule_dir, g)
                            platform = "Sentinel-2C" if "S2C_" in item else "Sentinel-2B"
                            self.epochs[year] = {
                                "year": year,
                                "date": date_str,
                                "platform": platform,
                                "safe_dir": item_path,
                                "granule_path": granule_path,
                                "safe_name": item
                            }

    def get_available_years(self):
        return sorted(list(self.epochs.keys()))

    def _find_band_file(self, granule_path: str, band_name: str, resolution: str = "10m"):
        img_dir = os.path.join(granule_path, "IMG_DATA", f"R{resolution}")
        if not os.path.exists(img_dir):
            return None
        for f in os.listdir(img_dir):
            if f"_{band_name}_{resolution}.jp2" in f:
                return os.path.join(img_dir, f)
        return None

    def _load_epoch_data(self, granule_path: str, window: Window):
        """
        Loads B02, B03, B04, B08 (10m) and SCL (20m resampled to 10m) for a given window.
        """
        band_names = ["B02", "B03", "B04", "B08"]
        bands = []
        for b in band_names:
            p = self._find_band_file(granule_path, b, "10m")
            with rasterio.open(p) as src:
                data = src.read(1, window=window).astype(np.float32)
                bands.append(data)
                
        # SCL 20m -> 10m
        scl_p = self._find_band_file(granule_path, "SCL", "20m")
        with rasterio.open(scl_p) as src:
            scl_window = Window(
                col_off=window.col_off // 2,
                row_off=window.row_off // 2,
                width=window.width // 2,
                height=window.height // 2
            )
            scl_data = src.read(
                1, 
                window=scl_window, 
                out_shape=(window.height, window.width), 
                resampling=Resampling.nearest
            )
            
        valid_mask = np.isin(scl_data, VALID_SCL_VALUES)
        return np.stack(bands, axis=0), valid_mask, scl_data

    def apply_phenological_normalization(self, delta_ndvi, scl_a, scl_b):
        """
        Applies phenological baseline normalization to suppress widespread seasonal vegetation browning false alarms.
        """
        # Identify stable vegetation (SCL=4 in both epochs)
        stable_veg_mask = (scl_a == 4) & (scl_b == 4)
        
        # Calculate regional vegetative drift mu_pheno
        if np.any(stable_veg_mask):
            mu_pheno = np.median(delta_ndvi[stable_veg_mask])
        else:
            mu_pheno = 0.0
            
        # Subtract background drift from delta_ndvi
        delta_ndvi_adjusted = delta_ndvi - mu_pheno
        return delta_ndvi_adjusted, mu_pheno

    def apply_illumination_correction(self, bands_a, bands_b, valid_mask):
        """
        Illumination correction factor based on mean band ratio normalization.
        """
        if not np.any(valid_mask):
            return bands_a, bands_b
        
        # Calculate mean brightness for both epochs over valid pixels
        br_a = (bands_a[0] + bands_a[1] + bands_a[2]) / 3.0
        br_b = (bands_b[0] + bands_b[1] + bands_b[2]) / 3.0
        
        mean_br_a = np.mean(br_a[valid_mask])
        mean_br_b = np.mean(br_b[valid_mask])
        
        if mean_br_a > 0 and mean_br_b > 0:
            correction_factor = mean_br_a / mean_br_b
            # Apply correction to bands_b to match bands_a illumination
            bands_b_corrected = bands_b * correction_factor
            return bands_a, bands_b_corrected
        
        return bands_a, bands_b

    def analyze_window(self, window: Window, year_a: int = 2024, year_b: int = 2025):
        """
        Compares two epoch observations (year_a vs year_b) over a spatial window.
        Returns:
            - change_category_map (2D int array)
            - rgb_a (PIL Image)
            - rgb_b (PIL Image)
            - change_rgb (PIL Image)
            - stats (dict)
        """
        if year_a not in self.epochs:
            raise ValueError(f"Epoch year {year_a} not found in available datasets: {self.get_available_years()}")
        if year_b not in self.epochs:
            raise ValueError(f"Epoch year {year_b} not found in available datasets: {self.get_available_years()}")

        info_a = self.epochs[year_a]
        info_b = self.epochs[year_b]

        bands_a, valid_a, scl_a = self._load_epoch_data(info_a["granule_path"], window)
        bands_b, valid_b, scl_b = self._load_epoch_data(info_b["granule_path"], window)

        # Joint quality masking: valid ONLY if valid in both epochs
        joint_valid = valid_a & valid_b
        total_pixels = window.width * window.height

        bands_a, bands_b = self.apply_illumination_correction(bands_a, bands_b, joint_valid)

        # Spectral Indices
        # B02=0 (Blue), B03=1 (Green), B04=2 (Red), B08=3 (NIR)
        ndvi_a = (bands_a[3] - bands_a[2]) / (bands_a[3] + bands_a[2] + 1e-6)
        ndvi_b = (bands_b[3] - bands_b[2]) / (bands_b[3] + bands_b[2] + 1e-6)
        delta_ndvi_raw = ndvi_b - ndvi_a
        
        delta_ndvi, mu_pheno = self.apply_phenological_normalization(delta_ndvi_raw, scl_a, scl_b)

        ndwi_a = (bands_a[1] - bands_a[3]) / (bands_a[1] + bands_a[3] + 1e-6)
        ndwi_b = (bands_b[1] - bands_b[3]) / (bands_b[1] + bands_b[3] + 1e-6)
        delta_ndwi = ndwi_b - ndwi_a

        # Brightness (Surface Reflectance proxy for built-up)
        br_a = (bands_a[0] + bands_a[1] + bands_a[2]) / 3.0
        br_b = (bands_b[0] + bands_b[1] + bands_b[2]) / 3.0
        delta_br = (br_b - br_a) / (br_a + 1e-6)

        # Initialize categorical change map: 0 = Unchanged, 255 = Masked
        # Categories:
        # 1 = BUILT_UP_EXPANSION
        # 2 = VEGETATION_LOSS
        # 3 = VEGETATION_GAIN
        # 4 = WATER_VARIATION
        cat_map = np.zeros((window.height, window.width), dtype=np.uint8)

        # 1. Built-up expansion: brightness increased significantly with loss of vegetation
        built_mask = (delta_br > 0.35) & (delta_ndvi < -0.1) & joint_valid
        cat_map[built_mask] = 1

        # 2. Vegetation Loss (Clearance): significant drop in NDVI
        veg_loss_mask = (delta_ndvi < -0.20) & (~built_mask) & joint_valid
        cat_map[veg_loss_mask] = 2

        # 3. Vegetation Gain (Regrowth / Greening): significant increase in NDVI
        veg_gain_mask = (delta_ndvi > 0.20) & joint_valid
        cat_map[veg_gain_mask] = 3

        # 4. Water Variation: NDWI shift
        water_mask = (np.abs(delta_ndwi) > 0.30) & (cat_map == 0) & joint_valid
        cat_map[water_mask] = 4

        # Masked pixels (clouds, cloud shadows in either epoch)
        cat_map[~joint_valid] = 255

        # Confounder suppression: remove isolated single-pixel false alarms
        clean_cat = cat_map.copy()
        for cat in [1, 2, 3, 4]:
            bin_mask = (cat_map == cat)
            filtered = median_filter(bin_mask.astype(np.uint8), size=3)
            clean_cat[(clean_cat == cat) & (filtered == 0)] = 0

        # Calculate evidence statistics
        valid_count = int(np.sum(joint_valid))
        masked_count = total_pixels - valid_count
        
        built_count = int(np.sum(clean_cat == 1))
        veg_loss_count = int(np.sum(clean_cat == 2))
        veg_gain_count = int(np.sum(clean_cat == 3))
        water_count = int(np.sum(clean_cat == 4))
        unchanged_count = valid_count - (built_count + veg_loss_count + veg_gain_count + water_count)

        stats = {
            "total_pixels": total_pixels,
            "valid_pixels": valid_count,
            "valid_ratio": round(valid_count / total_pixels, 4),
            "masked_pixels": masked_count,
            "masked_ratio": round(masked_count / total_pixels, 4),
            "built_up_expansion_pixels": built_count,
            "built_up_expansion_pct": round((built_count / max(1, valid_count)) * 100, 2),
            "vegetation_loss_pixels": veg_loss_count,
            "vegetation_loss_pct": round((veg_loss_count / max(1, valid_count)) * 100, 2),
            "vegetation_gain_pixels": veg_gain_count,
            "vegetation_gain_pct": round((veg_gain_count / max(1, valid_count)) * 100, 2),
            "water_variation_pixels": water_count,
            "water_variation_pct": round((water_count / max(1, valid_count)) * 100, 2),
            "unchanged_pixels": max(0, unchanged_count),
            "unchanged_pct": round((max(0, unchanged_count) / max(1, valid_count)) * 100, 2),
            "total_change_pct": round(((built_count + veg_loss_count + veg_gain_count + water_count) / max(1, valid_count)) * 100, 2),
            "confidence_score": round(min(1.0, (valid_count / total_pixels) * 0.95), 2),
            "classification_standard": "DERIVED_SATELLITE_EVIDENCE",
            "epochs": {
                "baseline": f"{info_a['date']} ({info_a['platform']})",
                "comparison": f"{info_b['date']} ({info_b['platform']})"
            }
        }

        rgb_a = self._make_rgb_pil(bands_a)
        rgb_b = self._make_rgb_pil(bands_b)
        change_rgb = self._make_change_map_pil(clean_cat)

        return clean_cat, rgb_a, rgb_b, change_rgb, stats

    def _make_rgb_pil(self, bands):
        # B04=2, B03=1, B02=0
        rgb = np.stack([bands[2], bands[1], bands[0]], axis=-1)
        rgb = np.clip(rgb, 0, 2500) / 2500.0 * 255.0
        return Image.fromarray(rgb.astype(np.uint8))

    def _make_change_map_pil(self, cat_map):
        h, w = cat_map.shape
        rgb_out = np.zeros((h, w, 3), dtype=np.uint8)
        
        # Color palette:
        # 0: Unchanged -> Dark Charcoal [30, 41, 59]
        # 1: Built-up Expansion -> Red/Crimson [239, 68, 68]
        # 2: Vegetation Loss -> Amber/Orange [245, 158, 11]
        # 3: Vegetation Gain -> Emerald Green [16, 185, 129]
        # 4: Water Variation -> Sky Blue [14, 165, 233]
        # 255: Masked / Cloud -> Slate Grey [100, 116, 139]
        rgb_out[cat_map == 0] = [30, 41, 59]
        rgb_out[cat_map == 1] = [239, 68, 68]
        rgb_out[cat_map == 2] = [245, 158, 11]
        rgb_out[cat_map == 3] = [16, 185, 129]
        rgb_out[cat_map == 4] = [14, 165, 233]
        rgb_out[cat_map == 255] = [100, 116, 139]

        return Image.fromarray(rgb_out)

    def analyze_tile_by_bbox(self, bbox: list, year_a: int = 2024, year_b: int = 2025, tile_size: int = 256):
        """
        Analyzes a tile given its bounding box [minx, miny, maxx, maxy] in EPSG:32645.
        """
        ref_granule = self.epochs[year_a]["granule_path"]
        b02_path = self._find_band_file(ref_granule, "B02", "10m")
        with rasterio.open(b02_path) as src:
            window = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], src.transform)
            window = Window(
                col_off=int(round(window.col_off)),
                row_off=int(round(window.row_off)),
                width=tile_size,
                height=tile_size
            )
        return self.analyze_window(window, year_a, year_b)

    def analyze_tri_epoch_by_bbox(self, bbox: list, tile_size: int = 256):
        """
        Analyzes 2024, 2025, and 2026 simultaneously over the specified spatial window.
        Returns all 3 RGB observations, 2-year cumulative change map, and spectral progression.
        """
        ref_granule = self.epochs[2024]["granule_path"]
        b02_path = self._find_band_file(ref_granule, "B02", "10m")
        with rasterio.open(b02_path) as src:
            window = from_bounds(bbox[0], bbox[1], bbox[2], bbox[3], src.transform)
            window = Window(
                col_off=int(round(window.col_off)),
                row_off=int(round(window.row_off)),
                width=tile_size,
                height=tile_size
            )

        # Load bands for all 3 epochs
        bands_24, valid_24, _ = self._load_epoch_data(self.epochs[2024]["granule_path"], window)
        bands_25, valid_25, _ = self._load_epoch_data(self.epochs[2025]["granule_path"], window)
        bands_26, valid_26, _ = self._load_epoch_data(self.epochs[2026]["granule_path"], window)

        # RGBs
        rgb_24 = self._make_rgb_pil(bands_24)
        rgb_25 = self._make_rgb_pil(bands_25)
        rgb_26 = self._make_rgb_pil(bands_26)

        # Cumulative 2024 vs 2026 change
        cat_24_26, _, _, change_rgb_cumul, stats_cumul = self.analyze_window(window, year_a=2024, year_b=2026)
        _, _, _, _, stats_24_25 = self.analyze_window(window, year_a=2024, year_b=2025)
        _, _, _, _, stats_25_26 = self.analyze_window(window, year_a=2025, year_b=2026)

        # Spectral time series metrics
        def mean_metric(b, v):
            valid_b = b[:, v]
            if valid_b.size == 0:
                return 0.0, 0.0
            ndvi = (valid_b[3] - valid_b[2]) / (valid_b[3] + valid_b[2] + 1e-6)
            br = (valid_b[0] + valid_b[1] + valid_b[2]) / 3.0
            return float(np.mean(ndvi)), float(np.mean(br))

        m_ndvi_24, m_br_24 = mean_metric(bands_24, valid_24)
        m_ndvi_25, m_br_25 = mean_metric(bands_25, valid_25)
        m_ndvi_26, m_br_26 = mean_metric(bands_26, valid_26)

        time_series = {
            "years": [2024, 2025, 2026],
            "dates": [self.epochs[2024]["date"], self.epochs[2025]["date"], self.epochs[2026]["date"]],
            "platforms": [self.epochs[2024]["platform"], self.epochs[2025]["platform"], self.epochs[2026]["platform"]],
            "mean_ndvi": [round(m_ndvi_24, 4), round(m_ndvi_25, 4), round(m_ndvi_26, 4)],
            "mean_brightness": [round(m_br_24, 1), round(m_br_25, 1), round(m_br_26, 1)]
        }

        return {
            "rgb_2024": rgb_24,
            "rgb_2025": rgb_25,
            "rgb_2026": rgb_26,
            "change_rgb_cumulative": change_rgb_cumul,
            "stats_24_25": stats_24_25,
            "stats_25_26": stats_25_26,
            "stats_cumulative": stats_cumul,
            "time_series": time_series
        }

