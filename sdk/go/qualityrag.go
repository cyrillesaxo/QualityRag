package qualityrag

import (
 "errors"
 "sort"
 "time"
)

type Requirement struct { ID string `json:"id"`; MinIndependentSources int `json:"min_independent_sources,omitempty"`; MaxAgeSeconds *int64 `json:"max_age_seconds,omitempty"` }
type Pack struct { ID string `json:"id"`; Version string `json:"version"`; Requirements []Requirement `json:"requirements"` }
type Evidence struct { ID string `json:"id"`; RequirementID string `json:"requirement_id"`; Origin string `json:"origin"`; SourceRef string `json:"source_ref"`; Status string `json:"status"`; ObservedAt string `json:"observed_at"` }
type Finding struct { RequirementID string `json:"requirement_id"`; Verdict string `json:"verdict"`; IndependentSources int `json:"independent_sources"`; Reasons []string `json:"reasons"` }
type Result struct { Schema string `json:"schema"`; PackID string `json:"pack_id"`; PackVersion string `json:"pack_version"`; Verdict string `json:"verdict"`; Findings []Finding `json:"findings"` }

// Evaluate verifies caller-provided evidence metadata only; it cannot authenticate sources.
func Evaluate(pack Pack, witnesses []Evidence, now time.Time) (Result,error) {
 if pack.ID=="" || pack.Version=="" || len(pack.Requirements)==0 {return Result{},errors.New("invalid pack")}
 seen:=map[string]bool{}
 result:=Result{Schema:"qualityrag.result/v0.1",PackID:pack.ID,PackVersion:pack.Version,Verdict:"ADMIT",Findings:[]Finding{}}
 for _,r:=range pack.Requirements {
  if r.ID==""||seen[r.ID]||r.MinIndependentSources<0||(r.MaxAgeSeconds!=nil&&*r.MaxAgeSeconds<0) {return Result{},errors.New("invalid requirement")}
  seen[r.ID]=true
  min:=r.MinIndependentSources; if min==0 {min=1}
  origins:=map[string]bool{}; reason:=map[string]bool{}; contradiction:=false
  for _,e:=range witnesses {
   if e.RequirementID!=r.ID {continue}
   if e.ID==""||e.Origin==""||e.SourceRef==""|| (e.Status!="SUPPORTS"&&e.Status!="CONTRADICTS"&&e.Status!="UNKNOWN") {reason["INVALID_EVIDENCE"]=true;continue}
   observed,err:=time.Parse(time.RFC3339Nano,e.ObservedAt);if err!=nil {reason["INVALID_EVIDENCE"]=true;continue}
   age:=now.Sub(observed)
   if age<0 {reason["FUTURE_EVIDENCE"]=true;continue}
   if r.MaxAgeSeconds!=nil&&age>time.Duration(*r.MaxAgeSeconds)*time.Second {reason["STALE_EVIDENCE"]=true;continue}
   if e.Status=="CONTRADICTS" {contradiction=true} else if e.Status=="SUPPORTS" {origins[e.Origin]=true} else {reason["UNKNOWN_EVIDENCE"]=true}
  }
  verdict:="ADMIT"
  if contradiction {verdict="REFUSE";reason["CONTRADICTION"]=true} else if len(origins)<min {verdict="INCONCLUSIVE";reason["INSUFFICIENT_INDEPENDENT_EVIDENCE"]=true}
  if verdict=="REFUSE" {result.Verdict="REFUSE"} else if verdict=="INCONCLUSIVE"&&result.Verdict!="REFUSE" {result.Verdict="INCONCLUSIVE"}
  reasons:=[]string{};for s:=range reason {reasons=append(reasons,s)};sort.Strings(reasons)
  result.Findings=append(result.Findings,Finding{r.ID,verdict,len(origins),reasons})
 }
 return result,nil
}
