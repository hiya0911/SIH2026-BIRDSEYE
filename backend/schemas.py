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

class ImageSearchRequest(BaseModel):
    tile_id: str
    top_k: int = 5