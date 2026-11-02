use chrono::{DateTime,Utc};
use qualityrag::{evaluate,Evidence,Pack,Requirement};
use serde_json::Value;
use std::fs;
#[test]
fn shared_conformance(){
 let raw=fs::read_to_string("../../conformance/v0.1.json").unwrap();
 let suite:Value=serde_json::from_str(&raw).unwrap();
 let now:DateTime<Utc>=suite["as_of"].as_str().unwrap().parse().unwrap();
 let p=Pack{id:"conformance".into(),version:"1".into(),requirements:vec![Requirement{id:"r".into(),min_independent_sources:2,max_age_seconds:Some(3600)}]};
 for case in suite["cases"].as_array().unwrap(){
  let evidence:Vec<Evidence>=case["evidence"].as_array().unwrap().iter().map(|r|{
   let a=r.as_array().unwrap();
   let id=a[0].as_str().unwrap();
   Evidence{id:id.into(),requirement_id:"r".into(),origin:a[1].as_str().unwrap().into(),source_ref:format!("doc:{id}"),status:a[2].as_str().unwrap().into(),observed_at:a.get(3).and_then(|x|x.as_str()).unwrap_or("2026-11-02T10:00:00Z").into()}
  }).collect();
  let result=evaluate(&p,&evidence,now);
  let label=case["name"].as_str().unwrap();
  assert_eq!(result.verdict,case["verdict"].as_str().unwrap(),"{label}");
  let expected:Vec<String>=case["reasons"].as_array().unwrap().iter().map(|v|v.as_str().unwrap().to_string()).collect();
  assert_eq!(result.findings[0].reasons,expected,"{label}");
 }
}
