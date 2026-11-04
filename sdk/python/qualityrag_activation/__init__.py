"""Typed wire client for the authenticated QualityRag activation API."""
import base64
import json
from urllib.request import Request,urlopen


class Client:
    def __init__(self,base_url,token,*,timeout=10):
        if not isinstance(base_url,str) or not base_url.startswith(("http://127.0.0.1:","https://")):
            raise ValueError("Loopback HTTP or trusted HTTPS endpoint required")
        self.url=base_url.rstrip("/")
        self.token=base64.urlsafe_b64encode(json.dumps(token,separators=(",",":")).encode()).decode().rstrip("=")
        self.timeout=timeout

    def request(self,route,payload):
        if route not in {"validate","evaluate","fallback","source","status","gardener/state","gardener/proposals","gardener/event","gardener/outcome"}:
            raise ValueError("Unsupported SDK route")
        request=Request(self.url+"/api/"+route,data=json.dumps(payload,allow_nan=False).encode(),
                        headers={"Content-Type":"application/json","Authorization":"Bearer "+self.token},method="POST")
        with urlopen(request,timeout=self.timeout) as response:
            return json.load(response)

    def validate(self,schema,value):return self.request("validate",{"schema":schema,"value":value})
    def evaluate(self,**payload):return self.request("evaluate",payload)
    def trace(self,**payload):return self.evaluate(**payload)["trace"]
    def fallback(self,source_sha256):return self.request("fallback",{"source_sha256":source_sha256})
    def upload(self,raw):return self.request("source",{"base64":base64.b64encode(raw).decode()})
