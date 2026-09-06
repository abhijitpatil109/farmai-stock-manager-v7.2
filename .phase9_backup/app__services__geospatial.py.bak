from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from xml.etree import ElementTree as ET
from ..db import connection
from .activity_register import ActivityRegisterNotFound,ActivityRegisterValidation

KML_NS={"k":"http://www.opengis.net/kml/2.2"}
PLOT_CODE_RE=re.compile(r"\b(PLOT-\d{3})\b",re.I)
ACRE_M2=4046.8564224
OVERLAP_TOLERANCE_M2=25.0
INTERIOR_BUFFER_M=5.0
INTERIOR_MIN_RETAINED_RATIO=0.35

def parse_kml(data:bytes):
    try: root=ET.fromstring(data)
    except ET.ParseError as e: raise ActivityRegisterValidation(f"Invalid KML: {e}") from e
    out=[]; seen=set()
    for pm in root.findall(".//k:Placemark",KML_NS):
        name=pm.findtext("k:name",default="",namespaces=KML_NS).strip()
        m=PLOT_CODE_RE.search(name)
        if not m: continue
        code=m.group(1).upper()
        if code in seen: raise ActivityRegisterValidation(f"Duplicate placemark {code}.")
        raw=pm.findtext(".//k:Polygon/k:outerBoundaryIs/k:LinearRing/k:coordinates",default="",namespaces=KML_NS)
        pts=[]
        for token in raw.strip().split():
            parts=token.split(",")
            if len(parts)<2: continue
            lon,lat=float(parts[0]),float(parts[1])
            if not(-180<=lon<=180 and -90<=lat<=90): raise ActivityRegisterValidation("Coordinate out of range.")
            pts.append([lon,lat])
        if len(pts)<4: raise ActivityRegisterValidation(f"{code} has too few points.")
        if pts[0]!=pts[-1]: pts.append(pts[0][:])
        if len(set(map(tuple,pts[:-1])))<3: raise ActivityRegisterValidation(f"{code} has fewer than 3 distinct vertices.")
        out.append({"plot_code":code,"name":name,"geojson":{"type":"MultiPolygon","coordinates":[[pts]]}})
        seen.add(code)
    if not out: raise ActivityRegisterValidation("No PLOT-### polygons found in KML.")
    return out

def get_active_geometry(plot_id):
    with connection() as c:
        r=c.execute("""SELECT pg.*,ST_AsGeoJSON(pg.geom)::jsonb geojson,
          CASE WHEN pg.interior_geom IS NULL THEN NULL ELSE ST_AsGeoJSON(pg.interior_geom)::jsonb END interior_geojson
          FROM public.plot_geometries pg WHERE pg.plot_id=%s AND pg.active=true""",(plot_id,)).fetchone()
    if not r: raise ActivityRegisterNotFound("Active plot geometry not found.")
    return dict(r)

def import_kml(path,farm_code="FARM-BENDRI-001",source_reference="BENDRI-GEOMETRY-v1",created_by="phase9-installer"):
    path=Path(path); data=path.read_bytes(); checksum=hashlib.sha256(data).hexdigest(); features=parse_kml(data)
    with connection() as c:
      try:
        farm=c.execute("SELECT * FROM public.farms WHERE code=%s",(farm_code,)).fetchone()
        if not farm: raise ActivityRegisterNotFound(f"Farm {farm_code} not found.")
        plots={x["code"]:x for x in c.execute("SELECT * FROM public.plots WHERE farm_id=%s AND active=true",(farm["id"],)).fetchall()}
        missing=[f["plot_code"] for f in features if f["plot_code"] not in plots]
        if missing: raise ActivityRegisterValidation(f"KML plot codes absent from DB: {missing}")
        staged=[]
        for f in features:
            gj=json.dumps(f["geojson"],separators=(",",":"))
            valid=c.execute("""SELECT ST_IsValid(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)) valid,
              ST_Area(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)::geography) area""",(gj,gj)).fetchone()
            if not valid["valid"] or float(valid["area"] or 0)<=0: raise ActivityRegisterValidation(f"Invalid geometry {f['plot_code']}.")
            staged.append((f,plots[f["plot_code"]],gj,float(valid["area"])))
        for i in range(len(staged)):
            for j in range(i+1,len(staged)):
                overlap=c.execute("""SELECT ST_Area(ST_Intersection(
                  ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))::geography) m2""",
                  (staged[i][2],staged[j][2])).fetchone()["m2"] or 0
                if float(overlap)>OVERLAP_TOLERANCE_M2:
                    raise ActivityRegisterValidation(f"Plot overlap exceeds tolerance: {staged[i][0]['plot_code']}↔{staged[j][0]['plot_code']} {float(overlap):.2f}m².")
        result=[]
        for f,plot,gj,area in staged:
            gh=hashlib.sha256(gj.encode()).hexdigest()
            existing=c.execute("SELECT * FROM public.plot_geometries WHERE plot_id=%s AND geometry_hash=%s",(plot["id"],gh)).fetchone()
            if existing:
                result.append({"plot_code":f["plot_code"],"geometry_id":str(existing["id"]),"duplicate":True}); continue
            version=c.execute("SELECT COALESCE(max(geometry_version),0)+1 v FROM public.plot_geometries WHERE plot_id=%s",(plot["id"],)).fetchone()["v"]
            c.execute("UPDATE public.plot_geometries SET active=false,effective_to=CURRENT_DATE WHERE plot_id=%s AND active=true",(plot["id"],))
            row=c.execute("""WITH g AS (
              SELECT ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)) geom
            ), b AS (
              SELECT geom,ST_Multi(ST_Transform(ST_Buffer(ST_Transform(geom,3857),-%s),4326)) interior,
                     ST_Area(geom::geography) full_area FROM g
            )
            INSERT INTO public.plot_geometries(
              plot_id,geometry_version,source_type,source_reference,source_checksum,geom,interior_geom,centroid,
              area_m2,calculated_area_acres,geometry_hash,edge_sensitivity,metadata,created_by)
            SELECT %s,%s,'KML_IMPORT',%s,%s,geom,
              CASE WHEN NOT ST_IsEmpty(interior) AND ST_Area(interior::geography)>=full_area*%s THEN interior END,
              ST_Centroid(geom),full_area,full_area/%s,%s,
              CASE WHEN full_area<2500 THEN 'HIGH' ELSE 'NORMAL' END,
              %s::jsonb,%s FROM b RETURNING *""",
              (gj,INTERIOR_BUFFER_M,plot["id"],version,source_reference,checksum,INTERIOR_MIN_RETAINED_RATIO,
               ACRE_M2,gh,json.dumps({"kml_name":f["name"],"source_file":path.name}),created_by)).fetchone()
            result.append({"plot_code":f["plot_code"],"geometry_id":str(row["id"]),"duplicate":False,
                           "area_acres":float(row["calculated_area_acres"]),"interior_available":row["interior_geom"] is not None})
        c.commit(); return {"source_checksum":checksum,"plots":result}
      except Exception:
        c.rollback(); raise
