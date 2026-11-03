//! Explicit PackSpec authorities. HTTP transport for Studio is injected by the host.
use crate::{Pack,Requirement};
use serde_json::Value;
use sha2::{Digest,Sha256};
use std::collections::{HashMap,HashSet};
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;

pub type Loader = Box<dyn Fn() -> Result<Pack,String> + Send + Sync>;
pub type HttpGet = Arc<dyn Fn(&str,&str) -> Result<String,String> + Send + Sync>;

fn parse(raw:&str)->Result<Pack,String>{
 let v:Value=serde_json::from_str(raw).map_err(|e|e.to_string())?;
 let id=v.get("id").and_then(Value::as_str).filter(|x|!x.is_empty()).ok_or("missing id")?;
 let version=v.get("version").and_then(Value::as_str).filter(|x|!x.is_empty()).ok_or("missing version")?;
 let rows=v.get("requirements").and_then(Value::as_array).filter(|x|!x.is_empty()).ok_or("missing requirements")?;
 let mut seen=HashSet::new();
 let mut requirements=Vec::new();
 for row in rows{
  let rid=row.get("id").and_then(Value::as_str).filter(|x|!x.is_empty()).ok_or("invalid requirement id")?;
  if !seen.insert(rid.to_string()){return Err("duplicate requirement".into())}
  let minimum=match row.get("min_independent_sources"){Some(x)=>x.as_u64().filter(|x|*x>0).ok_or("invalid minimum")? as usize,None=>1};
  let age=match row.get("max_age_seconds"){Some(x)=>Some(x.as_i64().filter(|x|*x>=0).ok_or("invalid max age")?),None=>None};
  requirements.push(Requirement{id:rid.into(),min_independent_sources:minimum,max_age_seconds:age});
 }
 Ok(Pack{id:id.into(),version:version.into(),requirements})
}
pub fn internal(pack:Pack)->Result<Loader,String>{
 if pack.id.is_empty()||pack.version.is_empty()||pack.requirements.is_empty()||
  pack.requirements.iter().any(|r|r.id.is_empty()||r.min_independent_sources==0||r.max_age_seconds.is_some_and(|n|n<0)) {
  return Err("invalid embedded PackSpec".into())
 }
 let p=Arc::new(pack);
 Ok(Box::new(move||Ok((*p).clone())))
}
pub fn property(json:&str)->Result<Loader,String>{internal(parse(json)?)}
pub fn file(path:PathBuf)->Loader{
 Box::new(move||{
  let metadata=fs::metadata(&path).map_err(|e|e.to_string())?;
  if metadata.len()>262144{return Err("policy file too large".into())}
  parse(&fs::read_to_string(&path).map_err(|e|e.to_string())?)
 })
}
/// Studio requires HTTPS beyond loopback; transport must enforce TLS verification and timeout.
pub fn studio(base:&str,token:&str,service:&str,environment:&str,http_get:HttpGet)->Result<Loader,String>{
 let valid=|x:&str|!x.is_empty()&&x.chars().all(|c|c.is_ascii_alphanumeric()||"._-".contains(c));
 if !(base.starts_with("https://")||base.starts_with("http://127.0.0.1:")||base.starts_with("http://localhost:")) ||
  base.contains('@')||base.contains('?')||base.contains('#')||token.is_empty()||!valid(service)||!valid(environment){
  return Err("invalid Studio configuration / HTTPS required".into())
 }
 let endpoint=format!("{}/v1/resolve/{}/{}",base.trim_end_matches('/'),service,environment);
 let token=token.to_owned();let service=service.to_owned();let environment=environment.to_owned();
 Ok(Box::new(move||{
  let raw=http_get(&endpoint,&token)?;
  if raw.len()>262144{return Err("Studio response too large".into())}
  let envelope:Value=serde_json::from_str(&raw).map_err(|e|e.to_string())?;
  if envelope.get("status").and_then(Value::as_str)!=Some("APPROVED") ||
   envelope.get("serviceId").and_then(Value::as_str)!=Some(service.as_str()) ||
   envelope.get("environment").and_then(Value::as_str)!=Some(environment.as_str()) {return Err("Studio binding mismatch".into())}
  let policy=envelope.get("policy").ok_or("missing Studio policy")?;
  let expected=envelope.get("sha256").and_then(Value::as_str).ok_or("missing digest")?;
  let digest=format!("{:x}",Sha256::digest(serde_json::to_string(policy).map_err(|e|e.to_string())?.as_bytes()));
  if expected.len()!=64||!expected.chars().all(|c|c.is_ascii_hexdigit() && !c.is_ascii_uppercase())||expected!=digest {
   return Err("Studio digest mismatch".into())
  }
  parse(&serde_json::to_string(policy).map_err(|e|e.to_string())?)
 }))
}
pub fn from_properties(props:&HashMap<String,String>,embedded:Option<Pack>,http_get:Option<HttpGet>)->Result<Loader,String>{
 let get=|k:&str|props.get(k).map(String::as_str).filter(|x|!x.is_empty()).ok_or_else(||format!("missing {k}"));
 match get("qualityrag.packspec.source")?{
  "internal"=>internal(embedded.ok_or("missing embedded policy")?),
  "property"=>property(get("qualityrag.packspec.json")?),
  "file"=>Ok(file(PathBuf::from(get("qualityrag.packspec.path")?))),
  "studio"=>studio(get("qualityrag.registry.url")?,get("qualityrag.registry.token")?,
    get("qualityrag.service-id")?,get("qualityrag.environment")?,http_get.ok_or("HTTP transport required")?),
  _=>Err("unknown PackSpec mode".into())
 }
}
