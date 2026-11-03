package qualityrag

import (
 "context"
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "net/http"
 "net/http/httptest"
 "os"
 "path/filepath"
 "testing"
)
func TestPackSources(t *testing.T){
 p:=Pack{ID:"eu",Version:"1",Requirements:[]Requirement{{ID:"general"},{ID:"control"}}}
 load,err:=InternalPackSource(p);if err!=nil{t.Fatal(err)}
 p.ID="mutated"
 result,err:=load(context.Background());if err!=nil||result.ID!="eu"{t.Fatalf("snapshot: %v %v",result,err)}
 path:=filepath.Join(t.TempDir(),"policy.json")
 if err=os.WriteFile(path,[]byte(`{"id":"eu","version":"1","requirements":[{"id":"general"},{"id":"control"}]}`),0600);err!=nil{t.Fatal(err)}
 file,_:=FilePackSource(path)
 if _,err=file(context.Background());err!=nil{t.Fatal(err)}
 os.WriteFile(path,[]byte("{}"),0600)
 if _,err=file(context.Background());err==nil{t.Fatal("invalid policy admitted")}
}
func TestStudioDigest(t *testing.T){
 raw:=`{"id":"eu","version":"1","requirements":[{"id":"general"}]}`
 digest:=sha256.Sum256([]byte(raw))
 corrupt:=false
 server:=httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter,r *http.Request){
  hash:=hex.EncodeToString(digest[:]);if corrupt{hash="0000000000000000000000000000000000000000000000000000000000000000"}
  json.NewEncoder(w).Encode(map[string]any{"serviceId":"app","environment":"dev","status":"APPROVED","sha256":hash,"policy":json.RawMessage(raw)})
 }))
 defer server.Close()
 load,err:=StudioPackSource(server.URL,"secret","app","dev",server.Client());if err!=nil{t.Fatal(err)}
 if _,err=load(context.Background());err!=nil{t.Fatal(err)}
 corrupt=true
 if _,err=load(context.Background());err==nil{t.Fatal("tampered policy accepted")}
 if _,err=StudioPackSource("http://example.com","x","app","dev",nil);err==nil{t.Fatal("insecure registry accepted")}
}
