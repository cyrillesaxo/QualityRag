use qualityrag::{evaluate,Evidence,Pack,Requirement};
use serde_json::Value;
use chrono::{DateTime,Utc};
#[test]fn all_twelve_apx_examples(){
 let path=concat!(env!("CARGO_MANIFEST_DIR"),"/../../examples/apx-packspecs/fixtures.json");
 let f:Value=serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
 let at:DateTime<Utc>=f["as_of"].as_str().unwrap().parse().unwrap();
 let mut count=0;
 for domain in f["scenarios"].as_array().unwrap(){
  let raw=&domain["pack"];
  let pack=Pack{id:raw["id"].as_str().unwrap().into(),version:raw["version"].as_str().unwrap().into(),
   requirements:raw["requirements"].as_array().unwrap().iter().map(|r|Requirement{
    id:r["id"].as_str().unwrap().into(),min_independent_sources:1,max_age_seconds:None}).collect()};
  for case in domain["cases"].as_array().unwrap(){
   let evidence:Vec<Evidence>=case["evidence"].as_array().unwrap().iter().map(|e|Evidence{
    id:e["id"].as_str().unwrap().into(),requirement_id:e["requirement_id"].as_str().unwrap().into(),
    origin:e["origin"].as_str().unwrap().into(),source_ref:e["source_ref"].as_str().unwrap().into(),
    status:e["status"].as_str().unwrap().into(),observed_at:e["observed_at"].as_str().unwrap().into()
   }).collect();
   assert_eq!(evaluate(&pack,&evidence,at).verdict,case["expected"].as_str().unwrap(),
    "{}/{}",domain["id"],case["id"]);
   count+=1;
  }
 }
 assert_eq!(count,12);
}
