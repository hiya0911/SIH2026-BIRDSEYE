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
    aoi_bbox: Optional[list] = None
    aoi_polygon: Optional[list] = None

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

