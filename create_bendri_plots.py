#!/usr/bin/env python3
import json, os, sys, urllib.request, urllib.error

BASE_URL = os.getenv("FARMAI_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.getenv("FARMAI_API_KEY")
FARM_ID = os.getenv("FARMAI_FARM_ID")

if not API_KEY:
    sys.exit("ERROR: FARMAI_API_KEY is not set.")
if not FARM_ID:
    sys.exit("ERROR: FARMAI_FARM_ID is not set.")

plots = [
    {"farm_id": FARM_ID, "code": "PLOT-001", "name_en": "Nana", "name_mr": "नाना",
     "area": 1.6, "area_unit_code": "ACRE",
     "description_en": "Permanent physical plot locally known as Nana.",
     "description_mr": "नाना या स्थानिक नावाने ओळखला जाणारा कायमस्वरूपी भौतिक प्लॉट.",
     "created_by": "ADMIN"},
    {"farm_id": FARM_ID, "code": "PLOT-002", "name_en": "Teakwood", "name_mr": "सागवान",
     "area": 0.5, "area_unit_code": "ACRE",
     "description_en": "Permanent physical plot locally known as Teakwood.",
     "description_mr": "सागवान या स्थानिक नावाने ओळखला जाणारा कायमस्वरूपी भौतिक प्लॉट.",
     "created_by": "ADMIN"},
    {"farm_id": FARM_ID, "code": "PLOT-003", "name_en": "Adjacent to Home", "name_mr": "घराशेजारी",
     "area": 1.0, "area_unit_code": "ACRE",
     "description_en": "Permanent physical plot located adjacent to the home.",
     "description_mr": "घराशेजारी असलेला कायमस्वरूपी भौतिक प्लॉट.",
     "created_by": "ADMIN"},
    {"farm_id": FARM_ID, "code": "PLOT-004", "name_en": "2 Bighe", "name_mr": "बिघे",
     "area": 1.0, "area_unit_code": "ACRE",
     "description_en": "Permanent physical plot locally known as 2 Bighe.",
     "description_mr": "२ बिघे या स्थानिक नावाने ओळखला जाणारा कायमस्वरूपी भौतिक प्लॉट.",
     "created_by": "ADMIN"},
    {"farm_id": FARM_ID, "code": "PLOT-005", "name_en": "Kamble", "name_mr": "कांबळे",
     "area": 0.5, "area_unit_code": "ACRE",
     "description_en": "Permanent physical plot locally known as Kamble.",
     "description_mr": "कांबळे या स्थानिक नावाने ओळखला जाणारा कायमस्वरूपी भौतिक प्लॉट.",
     "created_by": "ADMIN"},
]

url = f"{BASE_URL}/api/v1/plots"
for plot in plots:
    data = json.dumps(plot, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "X-API-Key": API_KEY}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"\n{plot['code']} - {plot['name_en']} ({plot['name_mr']})")
            print(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"\nFAILED {plot['code']} HTTP {e.code}")
        print(e.read().decode("utf-8", errors="replace"))

print("\nFinished.")
