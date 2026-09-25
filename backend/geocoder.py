"""
BIRDSΣY3 — Fine-Grained Geographic Location & Geocoding Engine (Phase 5A)
Supports fine-grained location search across India (neighbourhoods, localities, villages,
towns, cities, districts, states, landmarks), coordinate parsing, bounding boxes,
OpenStreetMap Nominatim integration, and an enriched offline local places fallback catalog.
"""

import re
import logging
import requests
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Enriched India-wide offline location catalog for instant / fallback lookup
ENRICHED_LOCAL_CATALOG: Dict[str, Dict[str, Any]] = {
    # West Bengal & Kolkata Theater
    "kolkata": {
        "display_name": "Kolkata, West Bengal, India",
        "place_name": "Kolkata",
        "locality": "Kolkata Urban Core",
        "city": "Kolkata",
        "district": "Kolkata",
        "state": "West Bengal",
        "country": "India",
        "category": "place",
        "type": "city",
        "lat": 22.5726,
        "lon": 88.3639,
        "wgs_bbox": [88.2639, 22.4726, 88.4639, 22.6726]
    },
    "lake town": {
        "display_name": "Lake Town, Kolkata, West Bengal, India",
        "place_name": "Lake Town",
        "locality": "Lake Town",
        "city": "Kolkata",
        "district": "North 24 Parganas",
        "state": "West Bengal",
        "country": "India",
        "category": "place",
        "type": "suburb",
        "lat": 22.5976,
        "lon": 88.4026,
        "wgs_bbox": [88.3876, 22.5876, 88.4176, 22.6076]
    },
    "lake town, kolkata": {
        "display_name": "Lake Town, Kolkata, West Bengal, India",
        "place_name": "Lake Town",
        "locality": "Lake Town",
        "city": "Kolkata",
        "district": "North 24 Parganas",
        "state": "West Bengal",
        "country": "India",
        "category": "place",
        "type": "suburb",
        "lat": 22.5976,
        "lon": 88.4026,
        "wgs_bbox": [88.3876, 22.5876, 88.4176, 22.6076]
    },
    "lake town, kolkata, west bengal, india": {
        "display_name": "Lake Town, Kolkata, West Bengal, India",
        "place_name": "Lake Town",
        "locality": "Lake Town",
        "city": "Kolkata",
        "district": "North 24 Parganas",
        "state": "West Bengal",
        "country": "India",
        "category": "place",
        "type": "suburb",
        "lat": 22.5976,
        "lon": 88.4026,
        "wgs_bbox": [88.3876, 22.5876, 88.4176, 22.6076]
    },
    "new town": {
        "display_name": "New Town, Rajarhat, Kolkata, West Bengal, India",
        "place_name": "New Town",
        "locality": "New Town Tech Corridor",
        "city": "Kolkata",
        "district": "North 24 Parganas",
        "state": "West Bengal",
        "country": "India",
        "category": "place",
        "type": "suburb",
        "lat": 22.5850,
        "lon": 88.4600,
        "wgs_bbox": [88.4350, 22.5600, 88.4850, 22.6100]
    },
    "new town, kolkata": {
        "display_name": "New Town, Rajarhat, Kolkata, West Bengal, India",
        "place_name": "New Town",
        "locality": "New Town Tech Corridor",
        "city": "Kolkata",
        "district": "North 24 Parganas",
        "state": "West Bengal",
        "country": "India",
        "category": "place",
        "type": "suburb",
        "lat": 22.5850,
        "lon": 88.4600,
        "wgs_bbox": [88.4350, 22.5600, 88.4850, 22.6100]
    },
    "howrah": {
        "display_name": "Howrah, West Bengal, India",
        "place_name": "Howrah",
        "locality": "Howrah Urban District",
        "city": "Howrah",
        "district": "Howrah",
        "state": "West Bengal",
        "country": "India",
        "category": "place",
        "type": "city",
        "lat": 22.5958,
        "lon": 88.2636,
        "wgs_bbox": [88.2336, 22.5658, 88.2936, 22.6258]
    },
    "siliguri": {
        "display_name": "Siliguri, Darjeeling / Jalpaiguri, West Bengal, India",
        "place_name": "Siliguri",
        "locality": "Siliguri Metropolitan Region",
        "city": "Siliguri",
        "district": "Darjeeling",
        "state": "West Bengal",
        "country": "India",
        "category": "place",
        "type": "city",
        "lat": 26.7271,
        "lon": 88.4315,
        "wgs_bbox": [88.3815, 26.6771, 88.4815, 26.7771]
    },
    "darjeeling": {
        "display_name": "Darjeeling, West Bengal, India",
        "place_name": "Darjeeling",
        "locality": "Darjeeling Hill District",
        "city": "Darjeeling",
        "district": "Darjeeling",
        "state": "West Bengal",
        "country": "India",
        "category": "place",
        "type": "town",
        "lat": 27.0410,
        "lon": 88.2663,
        "wgs_bbox": [88.2363, 27.0110, 88.2963, 27.0710]
    },
    "salt lake": {
        "display_name": "Salt Lake Sector V, Bidhannagar, Kolkata, West Bengal, India",
        "place_name": "Salt Lake Sector V",
        "locality": "Sector V Tech Zone",
        "city": "Kolkata",
        "district": "North 24 Parganas",
        "state": "West Bengal",
        "country": "India",
        "category": "place",
        "type": "suburb",
        "lat": 22.5800,
        "lon": 88.4300,
        "wgs_bbox": [88.4100, 22.5600, 88.4500, 22.6000]
    },
    "sundarbans": {
        "display_name": "Sundarbans Biosphere Reserve, West Bengal, India",
        "place_name": "Sundarbans",
        "locality": "Sundarbans Delta Zone",
        "city": "Sundarbans",
        "district": "South 24 Parganas",
        "state": "West Bengal",
        "country": "India",
        "category": "natural",
        "type": "reserve",
        "lat": 21.9497,
        "lon": 88.9007,
        "wgs_bbox": [88.7007, 21.7497, 89.1007, 22.1497]
    },

    # Major Pan-India Metros & Regional Hubs
    "mumbai": {
        "display_name": "Mumbai, Maharashtra, India",
        "place_name": "Mumbai",
        "locality": "Mumbai Metropolis",
        "city": "Mumbai",
        "district": "Mumbai City",
        "state": "Maharashtra",
        "country": "India",
        "category": "place",
        "type": "city",
        "lat": 19.0760,
        "lon": 72.8777,
        "wgs_bbox": [72.7777, 18.9760, 72.9777, 19.1760]
    },
    "delhi": {
        "display_name": "Delhi, National Capital Territory, India",
        "place_name": "Delhi",
        "locality": "National Capital Region",
        "city": "Delhi",
        "district": "New Delhi",
        "state": "Delhi",
        "country": "India",
        "category": "place",
        "type": "city",
        "lat": 28.6139,
        "lon": 77.2090,
        "wgs_bbox": [77.1090, 28.5139, 77.3090, 28.7139]
    },
    "bengaluru": {
        "display_name": "Bengaluru, Karnataka, India",
        "place_name": "Bengaluru",
        "locality": "Bengaluru Urban",
        "city": "Bengaluru",
        "district": "Bengaluru Urban",
        "state": "Karnataka",
        "country": "India",
        "category": "place",
        "type": "city",
        "lat": 12.9716,
        "lon": 77.5946,
        "wgs_bbox": [77.4946, 12.8716, 77.6946, 13.0716]
    },
    "bangalore": {
        "display_name": "Bengaluru, Karnataka, India",
        "place_name": "Bengaluru",
        "locality": "Bengaluru Urban",
        "city": "Bengaluru",
        "district": "Bengaluru Urban",
        "state": "Karnataka",
        "country": "India",
        "category": "place",
        "type": "city",
        "lat": 12.9716,
        "lon": 77.5946,
        "wgs_bbox": [77.4946, 12.8716, 77.6946, 13.0716]
    },
    "chennai": {
        "display_name": "Chennai, Tamil Nadu, India",
        "place_name": "Chennai",
        "locality": "Chennai District",
        "city": "Chennai",
        "district": "Chennai",
        "state": "Tamil Nadu",
        "country": "India",
        "category": "place",
        "type": "city",
        "lat": 13.0827,
        "lon": 80.2707,
        "wgs_bbox": [80.1707, 12.9827, 80.3707, 13.1827]
    },
    "hyderabad": {
        "display_name": "Hyderabad, Telangana, India",
        "place_name": "Hyderabad",
        "locality": "Hyderabad District",
        "city": "Hyderabad",
        "district": "Hyderabad",
        "state": "Telangana",
        "country": "India",
        "category": "place",
        "type": "city",
        "lat": 17.3850,
        "lon": 78.4867,
        "wgs_bbox": [78.3867, 17.2850, 78.5867, 17.4850]
    },
    "pune": {
        "display_name": "Pune, Maharashtra, India",
        "place_name": "Pune",
        "locality": "Pune Urban",
        "city": "Pune",
        "district": "Pune",
        "state": "Maharashtra",
        "country": "India",
        "category": "place",
        "type": "city",
        "lat": 18.5204,
        "lon": 73.8567,
        "wgs_bbox": [73.7567, 18.4204, 73.9567, 18.6204]
    },
    "ahmedabad": {
        "display_name": "Ahmedabad, Gujarat, India",
        "place_name": "Ahmedabad",
        "locality": "Ahmedabad District",
        "city": "Ahmedabad",
        "district": "Ahmedabad",
        "state": "Gujarat",
        "country": "India",
        "category": "place",
        "type": "city",
        "lat": 23.0225,
        "lon": 72.5714,
        "wgs_bbox": [72.4714, 22.9225, 72.6714, 23.1225]
    },
    "dhaka": {
        "display_name": "Dhaka, Bangladesh",
        "place_name": "Dhaka",
        "locality": "Dhaka Division",
        "city": "Dhaka",
        "district": "Dhaka District",
        "state": "Dhaka",
        "country": "Bangladesh",
        "category": "place",
        "type": "city",
        "lat": 23.8103,
        "lon": 90.4125,
        "wgs_bbox": [90.3125, 23.7103, 90.5125, 23.9103]
    }
}

def parse_coordinate_string(q: str) -> Optional[Dict[str, float]]:
    """
    Parses various numeric coordinate input formats:
    - '22.5726, 88.3639'
    - '22.5726 88.3639'
    - '22.5726° N, 88.3639° E'
    - '22.5726 N 88.3639 E'
    Returns dict with 'lat' and 'lon' floats or None if not matching coordinate syntax.
    """
    cleaned = q.strip().replace("°", "").replace("N", "").replace("S", "").replace("E", "").replace("W", "")
    parts = [p.strip() for p in re.split(r'[,;\s]+', cleaned) if p.strip()]
    if len(parts) == 2:
        try:
            lat = float(parts[0])
            lon = float(parts[1])
            if "S" in q.upper():
                lat = -abs(lat)
            if "W" in q.upper():
                lon = -abs(lon)
            return {"lat": lat, "lon": lon}
        except ValueError:
            return None
    return None


def validate_coordinates(lat: float, lon: float):
    """Validates WGS84 latitude and longitude ranges."""
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        raise ValueError("Latitude and longitude must be numbers.")
    if lat < -90.0 or lat > 90.0:
        raise ValueError(f"Invalid latitude ({lat}). Must be between -90.0 and +90.0 degrees.")
    if lon < -180.0 or lon > 180.0:
        raise ValueError(f"Invalid longitude ({lon}). Must be between -180.0 and +180.0 degrees.")


def geocode_location(query: str) -> Dict[str, Any]:
    """
    Executes fine-grained location intelligence lookup.
    1. Coordinate search (validates lat/lon range)
    2. Instant local catalog lookup
    3. OpenStreetMap Nominatim live API fallback
    Returns standardized payload with candidate results list.
    """
    q_str = query.strip()
    if not q_str:
        return {
            "status": "error",
            "message": "Query string cannot be empty.",
            "query": query,
            "results": []
        }

    # 1. Try parsing numeric coordinates
    coords = parse_coordinate_string(q_str)
    if coords is not None:
        lat = coords["lat"]
        lon = coords["lon"]
        try:
            validate_coordinates(lat, lon)
        except ValueError as ve:
            return {
                "status": "invalid_coordinates",
                "message": str(ve),
                "query": query,
                "results": []
            }
        
        coord_item = {
            "display_name": f"Coordinates ({lat:.4f}° N, {lon:.4f}° E)",
            "lat": lat,
            "lon": lon,
            "place_name": f"{lat:.4f}° N, {lon:.4f}° E",
            "locality": "Coordinate Target",
            "city": "",
            "district": "",
            "state": "",
            "country": "",
            "category": "coordinates",
            "type": "point",
            "provider": "Coordinate Input",
            "confidence": 1.0,
            "wgs_bbox": [
                round(lon - 0.025, 6),
                round(lat - 0.025, 6),
                round(lon + 0.025, 6),
                round(lat + 0.025, 6)
            ]
        }
        return {
            "status": "success",
            "query": query,
            "location_type": "coordinates",
            "total": 1,
            "lat": lat,
            "lon": lon,
            "name": coord_item["display_name"],
            "place_type": "point",
            "city": "",
            "district": "",
            "state": "",
            "country": "",
            "provider": "Coordinate Input",
            "confidence": 1.0,
            "wgs_bbox": coord_item["wgs_bbox"],
            "results": [coord_item]
        }

    # 2. Check enriched local places catalog (instant resolution)
    q_lower = q_str.lower().strip()
    local_matches = []
    
    if q_lower in ENRICHED_LOCAL_CATALOG:
        match_item = dict(ENRICHED_LOCAL_CATALOG[q_lower])
        match_item["provider"] = "Offline Local Catalog"
        match_item["confidence"] = 0.95
        local_matches.append(match_item)
    else:
        for key, entry in ENRICHED_LOCAL_CATALOG.items():
            if key in q_lower or q_lower in key or entry["place_name"].lower() in q_lower:
                match_item = dict(entry)
                match_item["provider"] = "Offline Local Catalog"
                match_item["confidence"] = 0.85
                if match_item not in local_matches:
                    local_matches.append(match_item)
                if len(local_matches) >= 5:
                    break

    if local_matches:
        primary = local_matches[0]
        return {
            "status": "success",
            "query": query,
            "location_type": primary["type"],
            "total": len(local_matches),
            "lat": primary["lat"],
            "lon": primary["lon"],
            "name": primary["display_name"],
            "place_type": primary["type"],
            "city": primary["city"],
            "district": primary["district"],
            "state": primary["state"],
            "country": primary["country"],
            "provider": "Offline Local Catalog",
            "confidence": primary["confidence"],
            "wgs_bbox": primary["wgs_bbox"],
            "results": local_matches
        }

    # 3. Fallback to OpenStreetMap Nominatim live API
    headers = {
        "User-Agent": "BIRDSEYE3-SatelliteAnalystConsole/1.0 (contact@birdseye3.local)"
    }
    params = {
        "q": q_str,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 5,
    }
    
    osm_items = []
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=headers,
            timeout=1.5
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                for item in data:
                    try:
                        item_lat = float(item["lat"])
                        item_lon = float(item["lon"])
                        addr = item.get("address", {})
                        
                        locality = (
                            addr.get("suburb") or addr.get("neighbourhood") or 
                            addr.get("residential") or addr.get("village") or 
                            addr.get("quarter") or addr.get("locality") or 
                            item.get("name", "")
                        )
                        city = addr.get("city") or addr.get("town") or addr.get("municipality") or addr.get("city_district", "")
                        district = addr.get("county") or addr.get("state_district") or addr.get("district", "")
                        state = addr.get("state", "")
                        country = addr.get("country", "")
                        
                        bbox_raw = item.get("boundingbox")
                        if bbox_raw and len(bbox_raw) == 4:
                            south, north, west, east = [float(b) for b in bbox_raw]
                            wgs_bbox = [round(west, 6), round(south, 6), round(east, 6), round(north, 6)]
                        else:
                            wgs_bbox = [
                                round(item_lon - 0.025, 6),
                                round(item_lat - 0.025, 6),
                                round(item_lon + 0.025, 6),
                                round(item_lat + 0.025, 6)
                            ]

                        osm_items.append({
                            "display_name": item.get("display_name", q_str),
                            "lat": item_lat,
                            "lon": item_lon,
                            "place_name": item.get("name", locality or q_str),
                            "locality": locality,
                            "city": city,
                            "district": district,
                            "state": state,
                            "country": country,
                            "category": item.get("category") or item.get("class", "place"),
                            "type": item.get("type", "locality"),
                            "provider": "OpenStreetMap Nominatim",
                            "confidence": round(float(item.get("importance", 0.5)), 2),
                            "wgs_bbox": wgs_bbox
                        })
                    except Exception as parse_err:
                        logger.debug(f"Error parsing OSM item: {parse_err}")
    except Exception as net_err:
        logger.warning(f"OpenStreetMap Nominatim geocoding network call failed or timed out: {net_err}")

    if osm_items:
        primary = osm_items[0]
        return {
            "status": "success",
            "query": query,
            "location_type": primary["type"],
            "total": len(osm_items),
            "lat": primary["lat"],
            "lon": primary["lon"],
            "name": primary["display_name"],
            "place_type": primary["type"],
            "city": primary["city"],
            "district": primary["district"],
            "state": primary["state"],
            "country": primary["country"],
            "provider": "OpenStreetMap Nominatim",
            "confidence": primary["confidence"],
            "wgs_bbox": primary["wgs_bbox"],
            "results": osm_items
        }

    # 4. Not found response
    return {
        "status": "not_found",
        "message": f"LOCATION NOT FOUND: '{query}'. Check spelling or enter Latitude, Longitude coordinates.",
        "query": query,
        "results": []
    }
