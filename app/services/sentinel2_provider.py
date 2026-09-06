from __future__ import annotations
import hashlib,json,os,random,time
from datetime import timezone,timedelta
from urllib import request,parse,error

STAC_SEARCH_URL="https://stac.dataspace.copernicus.eu/v1/search"
TOKEN_URL="https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
STATS_URL="https://sh.dataspace.copernicus.eu/statistics/v1"
COLLECTION="sentinel-2-l2a"
PROCESSING_DATA_TYPE="sentinel-2-l2a"
ALGORITHM_VERSION="9.0.0"
TRANSIENT_HTTP={429,500,502,503,504}
TIMEOUT_SECONDS=30
MAX_RETRIES=3

EVALSCRIPT="\n".join([
"//VERSION=3",
"function setup(){return {input:[{bands:['B04','B05','B08','B11','SCL','dataMask']}],",
"output:[{id:'indices',bands:['NDVI','NDRE','NDMI'],sampleType:'FLOAT32'},",
"{id:'quality',bands:['VALID','CLOUD','SHADOW','VEGETATION'],sampleType:'FLOAT32'},",
"{id:'dataMask',bands:['indices','quality']}]};}",
"function safe(a,b){return (a+b)==0?0:(a-b)/(a+b);}",
"function evaluatePixel(s){",
"var excluded=(s.SCL==0||s.SCL==1||s.SCL==3||s.SCL==8||s.SCL==9||s.SCL==10||s.SCL==11);",
"var denomOk=((s.B08+s.B04)!=0&&(s.B08+s.B05)!=0&&(s.B08+s.B11)!=0)?1:0;\nvar idxMask=s.dataMask*(excluded?0:1)*denomOk;",
"var cloud=(s.SCL==8||s.SCL==9||s.SCL==10)?1:0;",
"var shadow=(s.SCL==3)?1:0;",
"var vegetation=(s.SCL==4)?1:0;",
"return {indices:[safe(s.B08,s.B04),safe(s.B08,s.B05),safe(s.B08,s.B11)],",
"quality:[idxMask,cloud,shadow,vegetation],dataMask:[idxMask,s.dataMask]};}"
])

class ProviderError(RuntimeError):
    def __init__(self,message,code="PROVIDER_ERROR",http_status=None):
        super().__init__(message); self.code=code; self.http_status=http_status

def canonical_json(v): return json.dumps(v,sort_keys=True,separators=(",",":"),default=str)
def fingerprint(v): return hashlib.sha256(canonical_json(v).encode()).hexdigest()

def _http_json(url,method="GET",payload=None,headers=None,retries=MAX_RETRIES,timeout=TIMEOUT_SECONDS):
    headers={"Accept":"application/json",**(headers or {})}; data=None
    if payload is not None:
        if isinstance(payload,dict):
            data=canonical_json(payload).encode(); headers.setdefault("Content-Type","application/json")
        else: data=payload
    last=None
    for attempt in range(retries+1):
        try:
            with request.urlopen(request.Request(url,data=data,headers=headers,method=method),timeout=timeout) as resp:
                raw=resp.read()
                if not raw: return {},resp.status
                try: return json.loads(raw),resp.status
                except json.JSONDecodeError as exc: raise ProviderError("Malformed provider JSON.","MALFORMED_JSON",resp.status) from exc
        except error.HTTPError as exc:
            body=exc.read().decode("utf-8","replace")[:1000]
            if exc.code in TRANSIENT_HTTP and attempt<retries:
                time.sleep(min(4.0,(2**attempt)+random.random()/4)); last=exc; continue
            raise ProviderError(f"Provider HTTP {exc.code}: {body}","HTTP_ERROR",exc.code) from exc
        except (error.URLError,TimeoutError) as exc:
            if attempt<retries:
                time.sleep(min(4.0,(2**attempt)+random.random()/4)); last=exc; continue
            raise ProviderError(f"Provider network failure: {exc}","NETWORK_ERROR") from exc
    raise ProviderError(f"Provider retry exhausted: {last}","RETRY_EXHAUSTED")

class CdseStacClient:
    def discover(self,geojson,date_from,date_to,max_cloud=80,limit=20):
        payload={"collections":[COLLECTION],"intersects":geojson,
          "datetime":f"{date_from.isoformat()}T00:00:00Z/{date_to.isoformat()}T23:59:59Z",
          "limit":limit,"sortby":[{"field":"datetime","direction":"desc"}],
          "filter":{"op":"<=","args":[{"property":"eo:cloud_cover"},float(max_cloud)]}}
        body,status=_http_json(STAC_SEARCH_URL,"POST",payload)
        features=body.get("features")
        if not isinstance(features,list): raise ProviderError("STAC response missing features array.","CONTRACT_ERROR",status)
        return payload,features,body

class SentinelHubStatsClient:
    def __init__(self): self._token=None; self._expires=0.0
    def token(self):
        if self._token and time.time()<self._expires-60: return self._token
        cid=os.getenv("COPERNICUS_CLIENT_ID"); secret=os.getenv("COPERNICUS_CLIENT_SECRET")
        if not cid or not secret: raise ProviderError("COPERNICUS_CLIENT_ID and COPERNICUS_CLIENT_SECRET are required.","CREDENTIALS_MISSING")
        encoded=parse.urlencode({"grant_type":"client_credentials","client_id":cid,"client_secret":secret}).encode()
        body,status=_http_json(TOKEN_URL,"POST",encoded,{"Content-Type":"application/x-www-form-urlencoded"})
        token=body.get("access_token")
        if not token: raise ProviderError("OAuth response missing access_token.","AUTH_CONTRACT_ERROR",status)
        self._token=token; self._expires=time.time()+int(body.get("expires_in") or 300); return token
    def stats(self,geojson,acquired_at):
        start=acquired_at.astimezone(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0); end=start+timedelta(days=1)
        iso=lambda x:x.isoformat().replace("+00:00","Z")
        payload={"input":{"bounds":{"geometry":geojson,"properties":{"crs":"http://www.opengis.net/def/crs/OGC/1.3/CRS84"}},
          "data":[{"type":PROCESSING_DATA_TYPE,"dataFilter":{"timeRange":{"from":iso(start),"to":iso(end)},"mosaickingOrder":"leastCC"}}]},
          "aggregation":{"timeRange":{"from":iso(start),"to":iso(end)},"aggregationInterval":{"of":"P1D"},
                         "evalscript":EVALSCRIPT,"resx":10,"resy":10},
          "calculations":{"default":{"statistics":{"default":{"percentiles":{"k":[10,50,90]}}}}}}
        body,status=_http_json(STATS_URL,"POST",payload,{"Authorization":f"Bearer {self.token()}"})
        if body.get("status") not in (None,"OK"): raise ProviderError(f"Statistical API status={body.get('status')}","CONTRACT_ERROR",status)
        if not isinstance(body.get("data"),list) or not body["data"]: raise ProviderError("Statistical API returned no intervals.","NO_DATA",status)
        return payload,body

def _stats(out,band):
    try:return out["bands"][band]["stats"]
    except (KeyError,TypeError):return {}

def parse_stats_response(body):
    rows=body.get("data") or []
    if not rows: raise ProviderError("Statistics response has no data.","NO_DATA")
    outputs=rows[0].get("outputs") or {}; idx=outputs.get("indices") or {}; quality=outputs.get("quality") or {}
    result={}
    for name in ("NDVI","NDRE","NDMI"):
        st=_stats(idx,name)
        if not st: raise ProviderError(f"Statistics response missing {name}.","CONTRACT_ERROR")
        p=st.get("percentiles") or {}
        result[name]={"min":st.get("min"),"max":st.get("max"),"mean":st.get("mean"),"stddev":st.get("stDev"),
          "median":p.get("50.0",p.get("50")),"p10":p.get("10.0",p.get("10")),"p90":p.get("90.0",p.get("90")),
          "sample_count":st.get("sampleCount"),"nodata_count":st.get("noDataCount")}
    q={}
    for name in ("VALID","CLOUD","SHADOW","VEGETATION"):
        st=_stats(quality,name); q[name.lower()+"_pixel_pct"]=None if st.get("mean") is None else float(st["mean"])*100
    return {"indices":result,"quality":q,"interval":rows[0].get("interval")}
