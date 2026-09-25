# BIRDSEYΣ3 — Interactive Analyst Satellite Map & Location/AOI Intelligence Workflow

## 1. Overview & Architecture

The **Interactive Satellite Analyst Map & AOI Console** provides a high-performance, analyst-centric spatial workspace integrated directly into the BIRDSEYΣ3 Earth Observation console.

### Key Capabilities
- **Geographic Location Search**: Search places (e.g. Kolkata, Siliguri, Haldia) or raw WGS84 coordinates (e.g. `23.8103, 90.4125`) using an offline place catalog and strict coordinate parser.
- **Interactive Leaflet Map**: Dark-themed GIS canvas with pan, zoom, scale indicator, and telemetry HUD (WGS84 Lat/Lon, UTM 45N Easting/Northing, Zoom level, Tile counts).
- **AOI Selection Modes**:
  - `POINT`: Select specific location, place marker, show exact coordinates.
  - `RECTANGLE`: Drag/click bounding box, show bounds and calculated area in $\text{km}^2$.
  - `POLYGON`: Multi-vertex drawing, close boundary, calculate surface area in $\text{km}^2$.
- **Real Satellite Footprints**: Interactive Leaflet layer rendering 909 pre-indexed Sentinel-2 Level-2A tile boundaries directly on the map.
- **Downstream Analysis Integration**: Connect selected AOI geometry (`bbox` or `polygon`) directly to `/api/aoi/query` and `/api/aoi/analyze` for multi-temporal change detection and spatial retrieval restriction.
- **Honest SAR Status Reporting**: Explictly renders `SENTINEL-1 SAR — NOT CACHED LOCALLY` when radar rasters are unavailable on disk. Zero data fabrication.

---

## 2. Location Search & Offline Geocoding

The system supports dual location search without external paid API dependencies:

1. **Place Name Search**:
   - Matches input against local offline catalog (`LOCAL_PLACES_CATALOG`) covering key regional cities and strategic corridors (Kolkata, Siliguri, Haldia, Durgapur, Asansol, Howrah, Salt Lake, Rajarhat, Sundarbans, Darjeeling, Kharagpur, Dhaka).
2. **Coordinate Input Fallback**:
   - Parses `latitude, longitude` format (e.g., `23.8103, 90.4125`).
   - Validates ranges: $-90.0 \le \text{lat} \le 90.0$ and $-180.0 \le \text{lon} \le 180.0$.
3. **Not Found Handling**:
   - If query does not match catalog and is not valid coordinates, returns explicit message: `LOCATION NOT FOUND (Use Latitude, Longitude coordinates)`. Never fabricates geocoding results.

---

## 3. AOI Selection Modes & Area Calculation

### AOI Modes
- **POINT**: Sets single target location with cyan pulsing marker. Uses small spatial buffer ($\approx 0.015^\circ$) to query intersecting catalog tiles.
- **RECTANGLE**: Interactive bounding box selection. Calculates bounding box $[min\_lon, min\_lat, max\_lon, max\_lat]$.
- **POLYGON**: Multi-point vertex selection (minimum 3 points). Allows double-click or closing-vertex click to finalize.

### Exact Surface Area Calculation
Surface area is computed without placeholder or dummy values:
- **Rectangle Area ($\text{km}^2$)**:
  $$\text{Width (km)} = |\text{max\_lon} - \text{min\_lon}| \times 111.32 \times \cos\left(\frac{\text{min\_lat} + \text{max\_lat}}{2} \times \frac{\pi}{180}\right)$$
  $$\text{Height (km)} = |\text{max\_lat} - \text{min\_lat}| \times 111.32$$
  $$\text{Area} = \text{Width} \times \text{Height}$$
- **Polygon Area ($\text{km}^2$)**:
  Calculated using local projection Shoelace formula converted from planar meters to $\text{km}^2$:
  $$\text{Area (m}^2) = \frac{1}{2} \left| \sum_{i=0}^{n-1} (x_i y_{i+1} - x_{i+1} y_i) \right|, \quad \text{Area (km}^2) = \frac{\text{Area (m}^2)}{1,000,000}$$

---

## 4. Backend Geospatial Endpoints

| Endpoint | Method | Input Payload | Description |
|---|---|---|---|
| `/api/location/search` | `GET` | `q` (query string) | Local offline place catalog lookup & coordinate parser. |
| `/api/aoi/footprints` | `GET` | `limit` (optional int) | Returns GeoJSON FeatureCollection of pre-indexed tile boundaries. |
| `/api/aoi/query` | `POST` | `AOIQueryRequest` (`bbox` or `polygon`) | Returns intersecting Sentinel-2 tiles sorted by overlap area. |
| `/api/aoi/analyze` | `POST` | `AOIAnalyzeRequest` (`bbox` or `tile_id`) | Executes tri-epoch change detection over selected spatial boundary. |
| `/api/search/semantic` | `POST` | `SemanticSearchRequest` (`aoi_bbox`, `aoi_polygon`) | Restricts zero-shot CLIP semantic retrieval to tiles within selected AOI. |

---

## 5. Security & Input Validation

The system enforces strict input validation across all geospatial endpoints:
- **Latitude Range Check**: $-90.0 \le \text{lat} \le 90.0$ (returns HTTP 400 Bad Request if violated).
- **Longitude Range Check**: $-180.0 \le \text{lon} \le 180.0$ (returns HTTP 400 Bad Request if violated).
- **Rectangle Ordering Check**: $\text{min\_lon} < \text{max\_lon}$ and $\text{min\_lat} < \text{max\_lat}$.
- **Polygon Structure Check**: Minimum 3 valid coordinate pairs.
- **Path & URL Security**: System does not accept arbitrary filesystem paths or external URLs from frontend inputs.

---

## 6. How AOI Feeds Downstream Analysis

1. **Analyst Selection**: The analyst selects a Point, Rectangle, or Polygon on the interactive map.
2. **Catalog Query**: The frontend POSTs geometry to `/api/aoi/query`, identifying all intersecting Sentinel-2 tiles.
3. **AOI Information Panel**: Displays selected geometry type, coordinates, calculated area ($\text{km}^2$), matching scenes count, temporal coverage (`2024-02-23 to 2026-02-28`), sensors (`Sentinel-2 MSI Optical`), and SAR status.
4. **Analysis Handoff**: Clicking "Proceed to AOI Change Analysis" triggers `/api/aoi/analyze`, passing actual spatial bounds into the multi-epoch change detection pipeline.
5. **Spatial Retrieval Restriction**: Active AOI coordinates can be attached to `/api/search/semantic` requests to restrict zero-shot CLIP queries strictly to the analyst's selected region of interest.
