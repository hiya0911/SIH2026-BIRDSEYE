# BIRDSΣY3 — Analyst Map & Location Intelligence Architecture (Phase 5A)

## 1. Overview & System Objectives

Phase 5A replaces the legacy API-key-dependent basemap and enhances the geospatial location engine. The updated Analyst Map console provides real geographic map rendering, India-wide navigation, fine-grained location intelligence search (neighborhoods, localities, villages, towns, cities, districts, states, and coordinates), search suggestions, structured location metadata inspection, and graceful imagery availability indicators.

---

## 2. Geographic Map Providers & Layer Strategy

The system implements a multi-provider basemap strategy using standard Leaflet GIS architecture without any paid API key dependencies:

1. **Primary Vector Basemap: OpenStreetMap Standard**
   - **Tile URL:** `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`
   - **Key Dependency:** None (100% Free, Public OpenStreetMap Tile Infrastructure)
   - **Capabilities:** High-density vector-rendered roads, localities, neighborhoods, rivers, boundaries, and place names across all of India.

2. **Secondary Satellite Basemap: Esri World Imagery**
   - **Tile URL:** `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`
   - **Key Dependency:** None
   - **Capabilities:** Real optical satellite coverage for visual landscape inspection across India.

3. **Tertiary Styled Basemap: CartoDB Dark Matter**
   - **Tile URL:** `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png`
   - **Capabilities:** Dark analyst aesthetic basemap styling.

4. **Layer Switcher Control:**
   - Integrated into top-right map corner (`L.control.layers`) allowing analysts to toggle between vector, satellite, and dark modes seamlessly.

---

## 3. Geocoding & Location Intelligence Engine

The backend location engine (`backend/geocoder.py`) processes location queries via a 3-tier resolution pipeline:

1. **Tier 1 — Numeric Coordinate Parser & Validator:**
   - Recognizes inputs such as `22.5726, 88.3639`, `22.5726 88.3639`, `22.5726° N, 88.3639° E`.
   - Validates latitude in `[-90.0, +90.0]` and longitude in `[-180.0, +180.0]`.
   - Returns structured `location_type: "coordinates"`. Invalid coordinates return HTTP 400 with exact error details.

2. **Tier 2 — OpenStreetMap Nominatim Live Geocoding API:**
   - **API Endpoint:** `https://nominatim.openstreetmap.org/search`
   - **Parameters:** `q`, `format=jsonv2`, `addressdetails=1`, `limit=5`
   - **User-Agent:** `BIRDSEYE3-SatelliteAnalystConsole/1.0`
   - **Timeout:** 3.5 seconds
   - **Capabilities:** Resolves fine-grained locations including neighborhoods ("Lake Town, Kolkata"), localities ("Salt Lake Sector V"), towns ("Siliguri"), districts ("North 24 Parganas"), states ("West Bengal"), and major metro hubs ("Mumbai", "Delhi", "Bengaluru").
   - Returns structured administrative hierarchy: `locality`, `city`, `district`, `state`, `country`, `category`, `type`, `confidence` score, and `wgs_bbox`.

3. **Tier 3 — Enriched Offline Local Places Catalog:**
   - Fallback catalog containing structured metadata for Indian cities, strategic theaters, and localities (Kolkata, Lake Town, Siliguri, Howrah, New Town, Salt Lake, Sundarbans, Darjeeling, Delhi, Mumbai, Bengaluru, Chennai, Hyderabad, Pune, Ahmedabad, Dhaka).
   - Engaged automatically when offline or if online network calls fail.

---

## 4. Search Suggestions & UI Handoff

- **Live Debounced Search:** As the analyst types into the search bar, candidate location results populate an interactive dropdown menu (`#map-search-suggestions`).
- **Disambiguation:** If a query yields multiple matching localities (e.g. "Lake Town"), the UI displays candidate matches with category badges (`SUBURB`, `CITY`, `COORDINATES`) and administrative breadcrumbs. The analyst selects the exact intended result.
- **Map & AOI Handoff:**
  - Map smoothly flies to target coordinates (`state.map.flyTo`).
  - Circle marker is placed with location tooltip.
  - Coordinate input fields (`#coord-lat-input`, `#coord-lon-input`) auto-sync.
  - Full location intelligence card renders display name, coordinates, category/type, city/district, state/country, provider source, and relevance confidence.

---

## 5. Local Satellite Imagery Catalog Differentiation

The system distinguishes between **Geographic Location Availability** and **Local Staged Imagery Availability**:

- **Geographic Search Range:** India-wide (and global).
- **Staged Local Sentinel-2 Dataset:** Focused on Kolkata / Hooghly Basin / Sundarbans theater (909 indexed Level-2A tile patches).
- **UI Differentiating Indicator:**
  - If intersecting tiles are found in catalog: `✓ LOCAL SENTINEL-2 IMAGERY AVAILABLE (X TILES)` (Green Pill + Intersecting Tiles List + Change Analysis Handoff).
  - If no local tiles exist for searched region (e.g. Mumbai, Delhi): `⚠️ NO LOCAL TILES FOR THIS REGION (MAP NAVIGATION ACTIVE)` (Amber Pill + Informational Notice explaining that geographic search and map navigation are active while staged imagery is regional).

---

## 6. Offline Limitations & Fallback Behavior

| Operational Context | System Behavior |
| :--- | :--- |
| **Fully Online** | Live OpenStreetMap / Esri satellite basemaps + Nominatim fine-grained geocoding API + Local 909-tile imagery catalog. |
| **Offline / Air-Gapped** | Geocoder falls back to enriched local places catalog and coordinate parser. Map background displays clean console styling (`#060913`). All AOI drawing, geometry calculations, and 909-tile local satellite retrieval remain 100% operational. |
| **Tile Load Error** | Non-intrusive error trap sets fallback dark background without crashing Leaflet or UI. |

---

## 7. Supported Search Formats

- Neighborhoods & Localities: `"Lake Town, Kolkata, West Bengal, India"`, `"Salt Lake Sector V"`, `"New Town, Kolkata"`
- Cities & Towns: `"Kolkata"`, `"Siliguri"`, `"Howrah"`, `"Darjeeling"`, `"Mumbai"`, `"Delhi"`, `"Bengaluru"`
- Coordinate Pairs: `"22.5726, 88.3639"`, `"22.5726 88.3639"`, `"22.5726° N, 88.3639° E"`
