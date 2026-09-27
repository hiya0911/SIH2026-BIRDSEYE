from typing import Optional
from pydantic import BaseModel

class Location(BaseModel):
    name: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

class SearchRequest(BaseModel):
    query: str
    location: Optional[Location] = None
    from_year: int
    to_year: int

class SemanticSearchRequest(BaseModel):
    spectral_gate: bool = False
    action_mode: bool = False
    query: str
    top_k: int = 5
    sensor_filter: Optional[str] = "ALL"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    aoi_bbox: Optional[list] = None
    aoi_polygon: Optional[list] = None
    diversity_control: bool = True

class MultimodalSearchRequest(BaseModel):
    query: Optional[str] = None
    text_weight: float = 0.5
    image_weight: float = 0.5
    top_k: int = 12
    spectral_gate: bool = True
    action_mode: bool = False
    sensor_filter: Optional[str] = "ALL"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    aoi_bbox: Optional[list] = None
    aoi_polygon: Optional[list] = None
    diversity_control: bool = True

class ImageSearchRequest(BaseModel):
    tile_id: str
    top_k: int = 5

class AOIQueryRequest(BaseModel):
    bbox: Optional[list] = None # [min_lon, min_lat, max_lon, max_lat]
    polygon: Optional[list] = None # [[lon, lat], ...]
    limit: Optional[int] = 30

class AOIAnalyzeRequest(BaseModel):
    bbox: Optional[list] = None
    tile_id: Optional[str] = None

class PreprocessingPipelineRequest(BaseModel):
    year: int = 2024
    tile_id: Optional[str] = None
    bbox: Optional[list] = None
    baseline_year: int = 2024

class CopernicusSearchRequest(BaseModel):
    sensor: Optional[str] = "SENTINEL-2"
    collection: Optional[str] = None
    bbox: Optional[list] = None
    polygon: Optional[list] = None
    point: Optional[list] = None
    location_name: Optional[str] = None
    region: Optional[str] = None
    start_date: Optional[str] = "2024-01-01"
    end_date: Optional[str] = "2026-12-31"
    max_cloud_cover: Optional[float] = 100.0
    limit: Optional[int] = 10


from enum import Enum

class AnalystDecisionEnum(str, Enum):
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"
    FLAG = "FLAG"

class CaseCreateRequest(BaseModel):
    tile_id: str
    aoi_name: Optional[str] = None
    notes: Optional[str] = None

class AnalystReviewRequest(BaseModel):
    decision: AnalystDecisionEnum
    rationale: str
    analyst_id: Optional[str] = "analyst"
    case_id: Optional[str] = None
    tile_id: Optional[str] = None
    change_id: Optional[str] = None


class MultiTemporalChangeRequest(BaseModel):
    bbox: Optional[list] = None
    polygon: Optional[list] = None
    point: Optional[list] = None
    start_date: Optional[str] = "2024-01-01"
    end_date: Optional[str] = "2026-12-31"
    sensor: Optional[str] = "SENTINEL-2"


class RasterIngestRequest(BaseModel):
    filepath: str
    source_label: Optional[str] = "Analyst Manual Import"


class CopernicusAcquireRequest(BaseModel):
    scene_id: str
    collection: Optional[str] = "sentinel-2-l2a"
    sensor: Optional[str] = "SENTINEL-2"
    acquisition_time: Optional[str] = None
    asset_key: Optional[str] = "visual"
    asset_url: Optional[str] = None
    bbox: Optional[list] = None
    geometry: Optional[dict] = None


class SimilarSiteRequest(BaseModel):
    tile_id: Optional[str] = None
    bbox: Optional[list] = None
    polygon: Optional[list] = None
    point: Optional[list] = None
    location_name: Optional[str] = None
    region: Optional[str] = None
    text_query: Optional[str] = None
    top_k: Optional[int] = 10
    max_distance_km: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    sensor: Optional[str] = "ALL"
    cluster_id: Optional[int] = None




