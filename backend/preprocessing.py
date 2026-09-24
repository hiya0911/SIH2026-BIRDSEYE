import os
import rasterio
import numpy as np
from rasterio.enums import Resampling
from rasterio.windows import Window
import logging
from rasterio.warp import calculate_default_transform, reproject, Resampling as WarpResampling
import scipy.fft as fft
import scipy.ndimage as ndimage

logger = logging.getLogger(__name__)

# SCL classification mapping (Sentinel-2)
SCL_CLASSES = {
    "NO_DATA": 0,
    "SATURATED": 1,
    "DARK_AREA": 2,
    "CLOUD_SHADOW": 3,
    "VEGETATION": 4,
    "NOT_VEGETATED": 5,
    "WATER": 6,
    "UNCLASSIFIED": 7,
    "CLOUD_MEDIUM": 8,
    "CLOUD_HIGH": 9,
    "THIN_CIRRUS": 10,
    "SNOW": 11,
}

# valid pixels for analysis (exclude clouds, shadows, nodata, saturated)
VALID_SCL_VALUES = [4, 5, 6, 7, 11, 2]

class Preprocessor:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.l2a_granule_path = self._find_granule_path()
        if not self.l2a_granule_path:
            raise FileNotFoundError("Could not find a valid L2A GRANULE directory in the dataset.")

    def _find_granule_path(self):
        # 1. Direct GRANULE folder
        granule_dir = os.path.join(self.data_dir, "GRANULE")
        if os.path.exists(granule_dir):
            for item in os.listdir(granule_dir):
                if item.startswith("L2A_"):
                    return os.path.join(granule_dir, item)
        # 2. Check inside any *.SAFE directory
        if os.path.exists(self.data_dir):
            for entry in os.listdir(self.data_dir):
                if entry.endswith(".SAFE"):
                    g_sub = os.path.join(self.data_dir, entry, "GRANULE")
                    if os.path.exists(g_sub):
                        for item in os.listdir(g_sub):
                            if item.startswith("L2A_"):
                                return os.path.join(g_sub, item)
        return None


    def _find_band_file(self, band_name: str, resolution: str = "10m"):
        img_data_dir = os.path.join(self.l2a_granule_path, "IMG_DATA", f"R{resolution}")
        if not os.path.exists(img_data_dir):
            return None
        for f in os.listdir(img_data_dir):
            if f"_{band_name}_{resolution}.jp2" in f:
                return os.path.join(img_data_dir, f)
        return None

    def load_and_resample_scl(self, target_meta, window=None):
        """
        Loads the 20m SCL band and resamples it to match the target 10m metadata/window.
        """
        scl_file = self._find_band_file("SCL", "20m")
        if not scl_file:
            raise FileNotFoundError("SCL band not found.")

        with rasterio.open(scl_file) as src:
            # We want to read the window corresponding to the 10m window.
            # SCL is 20m, meaning 1 pixel in SCL is 2 pixels in 10m.
            if window is not None:
                scl_window = Window(
                    col_off=window.col_off // 2,
                    row_off=window.row_off // 2,
                    width=window.width // 2,
                    height=window.height // 2
                )
            else:
                scl_window = None

            # Determine shape based on 10m window/meta
            out_shape = (
                1,
                window.height if window else target_meta['height'],
                window.width if window else target_meta['width']
            )
            
            scl_data = src.read(
                1,
                window=scl_window,
                out_shape=(out_shape[1], out_shape[2]),
                resampling=Resampling.nearest
            )
        return scl_data

    def load_10m_bands(self, bands=["B02", "B03", "B04", "B08"], window=None):
        """
        Loads the specified 10m bands.
        Returns a stacked numpy array (bands, height, width) and metadata.
        """
        stacked = []
        target_meta = None

        for idx, band in enumerate(bands):
            band_file = self._find_band_file(band, "10m")
            if not band_file:
                raise FileNotFoundError(f"Band {band} not found.")

            with rasterio.open(band_file) as src:
                if target_meta is None:
                    target_meta = src.meta.copy()
                    if window:
                        target_meta.update({
                            'height': window.height,
                            'width': window.width,
                            'transform': rasterio.windows.transform(window, src.transform)
                        })
                
                data = src.read(1, window=window)
                stacked.append(data)

        return np.stack(stacked, axis=0), target_meta

    def create_quality_mask(self, scl_data):
        """
        Creates a boolean mask where True indicates a valid pixel.
        """
        mask = np.isin(scl_data, VALID_SCL_VALUES)
        return mask

    def process_window(self, window):
        """
        Process a specific window: load 10m bands, load SCL, create mask.
        Returns bands data and the mask.
        """
        bands_data, meta = self.load_10m_bands(window=window)
        scl_data = self.load_and_resample_scl(target_meta=meta, window=window)
        mask = self.create_quality_mask(scl_data)
        
        # Apply mask to data (set invalid pixels to 0 or nodata)
        # We will keep raw data but return mask alongside it so tiling can decide
        return bands_data, mask, meta

    def reproject_raster_window(self, source_data, src_transform, src_crs, dst_crs="EPSG:32645"):
        """
        Reprojects raster window to a canonical CRS.
        """
        src_height, src_width = source_data.shape[-2:]
        transform, width, height = calculate_default_transform(
            src_crs, dst_crs, src_width, src_height, *rasterio.transform.array_bounds(src_height, src_width, src_transform)
        )
        
        dst_shape = (source_data.shape[0], height, width)
        dst_data = np.zeros(dst_shape, source_data.dtype)
        
        reproject(
            source=source_data,
            destination=dst_data,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=transform,
            dst_crs=dst_crs,
            resampling=WarpResampling.nearest
        )
        return dst_data, transform


class PhaseCorrelationAligner:
    """
    Sub-Pixel Co-Registration Engine using 2D FFT Phase Correlation.
    """
    def __init__(self):
        pass

    def compute_translation(self, base_img, target_img):
        """
        Computes sub-pixel translation (dy, dx) to align target_img to base_img.
        Using phase correlation.
        """
        # FFT of both images
        F = fft.fft2(base_img)
        G = fft.fft2(target_img)
        
        # Cross-power spectrum
        cross_power = (F * np.conj(G)) / (np.abs(F * np.conj(G)) + 1e-10)
        
        # Inverse FFT to get cross-correlation
        r = fft.ifft2(cross_power)
        r = np.abs(r)
        
        # Find peak
        max_idx = np.unravel_index(np.argmax(r), r.shape)
        
        # Handle wraparound
        dy = max_idx[0]
        dx = max_idx[1]
        
        if dy > r.shape[0] // 2:
            dy -= r.shape[0]
        if dx > r.shape[1] // 2:
            dx -= r.shape[1]
            
        # Calculate naive RMSE based on peak value (pseudo-RMSE for registration quality)
        peak_val = r[max_idx]
        rmse = np.sqrt(1.0 - peak_val) if peak_val <= 1.0 else 0.0
        
        return dy, dx, rmse

    def align_images(self, base_bands, target_bands, reference_band_idx=2):
        """
        Aligns target_bands to base_bands using the Red band (B04) which is index 2.
        """
        base_ref = base_bands[reference_band_idx]
        target_ref = target_bands[reference_band_idx]
        
        dy, dx, rmse = self.compute_translation(base_ref, target_ref)
        
        aligned_target = np.zeros_like(target_bands)
        for i in range(target_bands.shape[0]):
            aligned_target[i] = ndimage.shift(target_bands[i], shift=(dy, dx), order=3)
            
        return aligned_target, (dy, dx), rmse
