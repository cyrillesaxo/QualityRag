package qualityrag
import ("testing";"time")
func TestGate(t *testing.T) {
 now:=time.Date(2026,11,2,10,5,0,0,time.UTC)
 max:=int64(3600)
 pack:=Pack{"p","1",[]Requirement{{ID:"r",MinIndependentSources:2,MaxAgeSeconds:&max}}}
 a:=Evidence{"a","r","A","doc:a","SUPPORTS","2026-11-02T10:00:00Z"}
 b:=Evidence{"b","r","B","doc:b","SUPPORTS","2026-11-02T10:00:00Z"}
 if out,_:=Evaluate(pack,[]Evidence{a,b},now);out.Verdict!="ADMIT" {t.Fatal(out)}
 b.Origin="A";if out,_:=Evaluate(pack,[]Evidence{a,b},now);out.Verdict!="INCONCLUSIVE" {t.Fatal(out)}
 b.Status="CONTRADICTS";if out,_:=Evaluate(pack,[]Evidence{a,b},now);out.Verdict!="REFUSE" {t.Fatal(out)}
}
