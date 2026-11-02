use chrono::{DateTime, Utc};
use std::collections::{BTreeSet, HashSet};
#[derive(Clone, Debug)]
pub struct Requirement {pub id:String,pub min_independent_sources:usize,pub max_age_seconds:Option<i64>}
pub struct Pack {pub id:String,pub version:String,pub requirements:Vec<Requirement>}
#[derive(Clone, Debug)]
pub struct Evidence {pub id:String,pub requirement_id:String,pub origin:String,pub source_ref:String,pub status:String,pub observed_at:String}
#[derive(Debug,PartialEq)]
pub struct Finding {pub requirement_id:String,pub verdict:String,pub independent_sources:usize,pub reasons:Vec<String>}
#[derive(Debug)]
pub struct Result {pub verdict:String,pub findings:Vec<Finding>}
/// Evaluates supplied evidence metadata, not source authenticity.
pub fn evaluate(pack:&Pack,evidence:&[Evidence],now:DateTime<Utc>)->Result {
    assert!(!pack.id.is_empty()&&!pack.version.is_empty()&&!pack.requirements.is_empty(),"invalid pack");
    let mut seen=HashSet::new();let mut findings=Vec::new();
    for r in &pack.requirements {
        assert!(!r.id.is_empty()&&seen.insert(&r.id)&&r.min_independent_sources>0&&r.max_age_seconds.map_or(true,|x|x>=0),"invalid requirement");
        let mut origins=HashSet::new();let mut reasons=BTreeSet::new();let mut contradiction=false;
        for e in evidence.iter().filter(|x|x.requirement_id==r.id) {
            if e.id.is_empty()||e.origin.is_empty()||e.source_ref.is_empty()||!["SUPPORTS","CONTRADICTS","UNKNOWN"].contains(&e.status.as_str()) {reasons.insert("INVALID_EVIDENCE");continue;}
            let observed=match DateTime::parse_from_rfc3339(&e.observed_at){Ok(t)=>t.with_timezone(&Utc),Err(_)=>{reasons.insert("INVALID_EVIDENCE");continue;}};
            let age=now.signed_duration_since(observed).num_milliseconds();
            if age<0 {reasons.insert("FUTURE_EVIDENCE");continue;}
            if r.max_age_seconds.is_some_and(|x|age> x*1000) {reasons.insert("STALE_EVIDENCE");continue;}
            match e.status.as_str() {"CONTRADICTS"=>contradiction=true,"SUPPORTS"=>{origins.insert(e.origin.clone());},_=>{reasons.insert("UNKNOWN_EVIDENCE");}}
        }
        let verdict=if contradiction {reasons.insert("CONTRADICTION");"REFUSE"}else if origins.len()<r.min_independent_sources {reasons.insert("INSUFFICIENT_INDEPENDENT_EVIDENCE");"INCONCLUSIVE"}else{"ADMIT"};
        findings.push(Finding{requirement_id:r.id.clone(),verdict:verdict.into(),independent_sources:origins.len(),reasons:reasons.into_iter().map(String::from).collect()});
    }
    let verdict=if findings.iter().any(|f|f.verdict=="REFUSE") {"REFUSE"}else if findings.iter().any(|f|f.verdict=="INCONCLUSIVE") {"INCONCLUSIVE"}else{"ADMIT"};
    Result{verdict:verdict.into(),findings}
}
#[cfg(test)]
mod tests{
use super::*;use chrono::TimeZone;
#[test]fn decisions(){
 let now=Utc.with_ymd_and_hms(2026,11,2,10,5,0).unwrap();
 let p=Pack{id:"p".into(),version:"1".into(),requirements:vec![Requirement{id:"r".into(),min_independent_sources:2,max_age_seconds:Some(3600)}]};
 let a=Evidence{id:"a".into(),requirement_id:"r".into(),origin:"A".into(),source_ref:"doc:a".into(),status:"SUPPORTS".into(),observed_at:"2026-11-02T10:00:00Z".into()};
 let mut b=a.clone();b.id="b".into();b.origin="B".into();
 assert_eq!(evaluate(&p,&[a.clone(),b.clone()],now).verdict,"ADMIT");
 b.origin="A".into();assert_eq!(evaluate(&p,&[a.clone(),b.clone()],now).verdict,"INCONCLUSIVE");
 b.status="CONTRADICTS".into();assert_eq!(evaluate(&p,&[a,b],now).verdict,"REFUSE");
}}
