package qualityrag
import ("encoding/json";"os";"testing";"time")
type suite struct {AsOf string `json:"as_of"`;Pack Pack `json:"pack"`;Cases []struct{Name string `json:"name"`;Evidence [][]string `json:"evidence"`;Verdict string `json:"verdict"`;Reasons []string `json:"reasons"`} `json:"cases"`}
func TestSharedConformance(t *testing.T){
 raw,err:=os.ReadFile("../../conformance/v0.1.json");if err!=nil{t.Fatal(err)}
 var s suite;if err=json.Unmarshal(raw,&s);err!=nil{t.Fatal(err)}
 now,err:=time.Parse(time.RFC3339,s.AsOf);if err!=nil{t.Fatal(err)}
 for _,c:=range s.Cases {t.Run(c.Name,func(t *testing.T){
  evidence:=[]Evidence{};for _,row:=range c.Evidence {stamp:="2026-11-02T10:00:00Z";if len(row)>3{stamp=row[3]};evidence=append(evidence,Evidence{ID:row[0],Origin:row[1],Status:row[2],RequirementID:"r",SourceRef:"doc:"+row[0],ObservedAt:stamp})}
  result,err:=Evaluate(s.Pack,evidence,now);if err!=nil{t.Fatal(err)}
  if result.Verdict!=c.Verdict {t.Fatalf("verdict: %s != %s",result.Verdict,c.Verdict)}
  got:=result.Findings[0].Reasons;if len(got)!=len(c.Reasons){t.Fatalf("reasons: %v != %v",got,c.Reasons)}
  for i:=range got{if got[i]!=c.Reasons[i]{t.Fatalf("reasons: %v != %v",got,c.Reasons)}}
 })}
}
