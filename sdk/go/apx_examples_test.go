package qualityrag
import (
 "encoding/json"
 "os"
 "testing"
 "time"
)
func TestAPXExampleFixtures(t *testing.T){
 var fixture struct{
  AsOf string `json:"as_of"`
  Scenarios []struct{
   ID string `json:"id"`
   Pack Pack `json:"pack"`
   Cases []struct{
    ID string `json:"id"`
    Expected string `json:"expected"`
    Evidence []Evidence `json:"evidence"`
   } `json:"cases"`
  } `json:"scenarios"`
 }
 b,err:=os.ReadFile("../../examples/apx-packspecs/fixtures.json");if err!=nil{t.Fatal(err)}
 if err=json.Unmarshal(b,&fixture);err!=nil{t.Fatal(err)}
 now,err:=time.Parse(time.RFC3339,fixture.AsOf);if err!=nil{t.Fatal(err)}
 count:=0
 for _,domain:=range fixture.Scenarios {
  for _,c:=range domain.Cases {
   out,err:=Evaluate(domain.Pack,c.Evidence,now);if err!=nil{t.Fatal(err)}
   if out.Verdict!=c.Expected {t.Errorf("%s/%s = %s expected %s",domain.ID,c.ID,out.Verdict,c.Expected)}
   count++
  }
 }
 if count!=12 {t.Fatalf("expected 12 cases, got %d",count)}
}
