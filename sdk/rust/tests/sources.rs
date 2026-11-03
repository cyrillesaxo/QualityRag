use qualityrag::sources;
use std::{sync::Arc,fs};
use sha2::{Digest,Sha256};
#[test]fn file_and_property_fail_closed(){
 let source=sources::property(r#"{"id":"eu","version":"1","requirements":[{"id":"general"},{"id":"control"}]}"#).unwrap();
 assert_eq!(source().unwrap().requirements.len(),2);
 let p=std::env::temp_dir().join(format!("qualityrag-{}.json",std::process::id()));
 fs::write(&p,"{}").unwrap();
 let load=sources::file(p.clone());
 assert!(load().is_err());
 fs::remove_file(p).unwrap();
 assert!(load().is_err());
}
#[test]fn studio_integrity(){
 let policy=r#"{"id":"eu","version":"1","requirements":[{"id":"general"}]}"#;
 let hash=format!("{:x}",Sha256::digest(policy.as_bytes()));
 let result=serde_json::json!({"serviceId":"app","environment":"dev","status":"APPROVED",
    "sha256":hash,"policy":serde_json::from_str::<serde_json::Value>(policy).unwrap()});
 let body=result.to_string();
 let loader=sources::studio("http://127.0.0.1:5055","token","app","dev",Arc::new(move|_,_|Ok(body.clone()))).unwrap();
 assert_eq!(loader().unwrap().id,"eu");
 let bad=sources::studio("http://example.com","token","app","dev",Arc::new(|_,_|Ok(String::new())));
 assert!(bad.is_err());
}
