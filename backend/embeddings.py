import torch
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import numpy as np
import rasterio

class EmbeddingExtractor:
    def __init__(self, model_name: str = "openai/clip-vit-base-patch32", local_files_only: bool = False):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        # For offline requirement, once downloaded, local_files_only should be True.
        # We will attempt local first, fallback to download if fails (for the very first run).
        try:
            self.model = CLIPModel.from_pretrained(model_name, local_files_only=True).to(self.device)
            self.processor = CLIPProcessor.from_pretrained(model_name, local_files_only=True)
        except Exception as e:
            if local_files_only:
                raise e
            print("Model not found locally, downloading and caching...")
            self.model = CLIPModel.from_pretrained(model_name).to(self.device)
            self.processor = CLIPProcessor.from_pretrained(model_name)

    def _normalize_image(self, img_array):
        """
        Normalizes a multi-spectral image array (C, H, W) to RGB 8-bit (H, W, 3).
        Assuming the bands passed are B04, B03, B02 (Red, Green, Blue) in the first 3 channels.
        If B02, B03, B04, B08 is the order, we need indices 2, 1, 0.
        """
        # Sentinel-2 data is often 12-bit (0-4095) or 16-bit. 
        # We clip to 3000 for standard visualization.
        # Our stacked bands order: B02, B03, B04, B08
        b02 = img_array[0]
        b03 = img_array[1]
        b04 = img_array[2]
        
        rgb = np.stack([b04, b03, b02], axis=-1)
        rgb = np.clip(rgb, 0, 3000) / 3000.0 * 255.0
        return rgb.astype(np.uint8)

    def extract_from_pil(self, pil_image: Image.Image):
        """
        Extracts 512-D normalized CLIP visual embedding directly from a PIL Image.
        """
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")

        inputs = self.processor(images=pil_image, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            image_features = self.model.get_image_features(**inputs)
            if hasattr(image_features, "pooler_output"):
                image_features = image_features.pooler_output
            elif hasattr(image_features, "image_embeds"):
                image_features = image_features.image_embeds
            elif not isinstance(image_features, torch.Tensor):
                image_features = image_features[0]
            
        # Normalize the embedding
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        return image_features.cpu().numpy()[0]

    def extract_from_tile(self, tile_path: str):
        """
        Loads a GeoTIFF tile, converts to RGB PIL Image, and extracts CLIP embeddings.
        Returns the embedding as a numpy array.
        """
        with rasterio.open(tile_path) as src:
            data = src.read() # (C, H, W)
            
        rgb_image = self._normalize_image(data)
        pil_image = Image.fromarray(rgb_image)
        return self.extract_from_pil(pil_image)

    def extract_from_text(self, text: str, ensemble: bool = True):
        """
        Extracts embedding for a text query with satellite domain prompt ensembling.
        """
        if ensemble:
            templates = [
                text,
                f"satellite imagery of {text}",
                f"aerial remote sensing view of {text}",
                f"orbital Earth observation of {text}",
                f"Sentinel-2 satellite observation showing {text}"
            ]
        else:
            templates = [text]

        inputs = self.processor(text=templates, return_tensors="pt", padding=True).to(self.device)
        
        with torch.no_grad():
            text_features = self.model.get_text_features(**inputs)
            if hasattr(text_features, "pooler_output"):
                text_features = text_features.pooler_output
            elif hasattr(text_features, "text_embeds"):
                text_features = text_features.text_embeds
            elif not isinstance(text_features, torch.Tensor):
                text_features = text_features[0]
            
            # Normalize each vector
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            if ensemble:
                # Average template vectors to synthesize robust satellite semantic representation
                mean_vec = text_features.mean(dim=0)
                mean_vec = mean_vec / mean_vec.norm(dim=-1)
                return mean_vec.cpu().numpy()
            else:
                return text_features.cpu().numpy()[0]
