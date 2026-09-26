from datetime import datetime

def create_search_document(
    query,
    location,
    lat,
    lon,
    from_year,
    to_year,
    change_data
):
    return {
        "query": query,
        "location": location,
        "latitude": lat,
        "longitude": lon,
        "from_year": from_year,
        "to_year": to_year,
        "years": abs(to_year - from_year) or 1,
        "change": change_data.get("total", 0),
        "change_breakdown": change_data,
        "created_at": datetime.utcnow()
    }

def create_tile_document(
    tile_id,
    filename,
    filepath,
    bbox,
    crs,
    valid_ratio,
    resolution,
    acquisition_datetime,
    source_scene,
    **kwargs
):
    doc = {
        "tile_id": tile_id,
        "filename": filename,
        "filepath": filepath,
        "bbox": bbox,
        "crs": crs,
        "valid_ratio": valid_ratio,
        "resolution": resolution,
        "acquisition_datetime": acquisition_datetime,
        "source_scene": source_scene,
        "created_at": datetime.utcnow()
    }
    doc.update(kwargs)
    return doc

def create_provenance_document(
    action,
    source_files,
    output_files,
    parameters,
    user="system"
):
    return {
        "action": action,
        "source_files": source_files,
        "output_files": output_files,
        "parameters": parameters,
        "user": user,
        "timestamp": datetime.utcnow()
    }