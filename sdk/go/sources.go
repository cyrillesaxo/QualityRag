package qualityrag

import (
 "bytes"
 "context"
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "net/http"
 "net/url"
 "os"
 "regexp"
 "strings"
 "time"
)

type PackSource func(context.Context) (Pack,error)
var segment=regexp.MustCompile(`^[A-Za-z0-9._-]+$`)
func checkedPack(p Pack)(Pack,error){
 if p.ID==""||p.Version==""||len(p.Requirements)==0{return Pack{},errors.New("invalid PackSpec")}
 ids:=map[string]bool{}
 for _,r:=range p.Requirements{
  if r.ID==""||ids[r.ID]||r.MinIndependentSources<0||(r.MaxAgeSeconds!=nil&&*r.MaxAgeSeconds<0){return Pack{},errors.New("invalid requirement")}
  ids[r.ID]=true
 }
 return p,nil
}
func parsePack(b []byte)(Pack,error) {
 var p Pack
 if err:=json.Unmarshal(b,&p);err!=nil{return Pack{},err}
 return checkedPack(p)
}
func InternalPackSource(p Pack)(PackSource,error) {
 raw,err:=json.Marshal(p);if err!=nil{return nil,err}
 if _,err=parsePack(raw);err!=nil{return nil,err}
 return func(context.Context)(Pack,error){return parsePack(raw)},nil
}
func PropertyPackSource(raw string)(PackSource,error){
 if strings.TrimSpace(raw)=="" {return nil,errors.New("missing inline policy")}
 p,err:=parsePack([]byte(raw));if err!=nil{return nil,err}
 return InternalPackSource(p)
}
func FilePackSource(path string)(PackSource,error){
 if strings.TrimSpace(path)==""{return nil,errors.New("missing policy file")}
 return func(context.Context)(Pack,error){
  f,err:=os.Open(path);if err!=nil{return Pack{},err};defer f.Close()
  b,err:=io.ReadAll(io.LimitReader(f,262145));if err!=nil{return Pack{},err}
  if len(b)>262144{return Pack{},errors.New("policy too large")}
  return parsePack(b)
 },nil
}
func StudioPackSource(base,token,service,environment string,client *http.Client)(PackSource,error){
 u,err:=url.Parse(base);if err!=nil{return nil,err}
 if u.User!=nil||u.RawQuery!=""||u.Fragment!=""||u.Hostname()==""||
  !(u.Scheme=="https"||(u.Scheme=="http"&&(u.Hostname()=="localhost"||u.Hostname()=="127.0.0.1"))){
  return nil,errors.New("HTTPS required outside loopback")
 }
 if token==""||!segment.MatchString(service)||!segment.MatchString(environment){return nil,errors.New("invalid Studio configuration")}
 if client==nil{client=&http.Client{Timeout:5*time.Second}}
 endpoint:=strings.TrimRight(base,"/")+"/v1/resolve/"+service+"/"+environment
 return func(ctx context.Context)(Pack,error){
  req,err:=http.NewRequestWithContext(ctx,"GET",endpoint,nil);if err!=nil{return Pack{},err}
  req.Header.Set("Authorization","Bearer "+token)
  res,err:=client.Do(req);if err!=nil{return Pack{},err};defer res.Body.Close()
  if res.StatusCode!=200{return Pack{},fmt.Errorf("Studio policy unavailable: HTTP %d",res.StatusCode)}
  body,err:=io.ReadAll(io.LimitReader(res.Body,262145));if err!=nil{return Pack{},err}
  if len(body)>262144{return Pack{},errors.New("Studio response too large")}
  var envelope struct{
   ServiceID string `json:"serviceId"`
   Environment string `json:"environment"`
   Status string `json:"status"`
   SHA string `json:"sha256"`
   Policy json.RawMessage `json:"policy"`
  }
  if err=json.Unmarshal(body,&envelope);err!=nil{return Pack{},err}
  if envelope.ServiceID!=service||envelope.Environment!=environment||envelope.Status!="APPROVED"{
   return Pack{},errors.New("unapproved or mismatched Studio policy")
  }
  var compact bytes.Buffer
  if err=json.Compact(&compact,envelope.Policy);err!=nil{return Pack{},err}
  actual:=sha256.Sum256(compact.Bytes())
  expected,err:=hex.DecodeString(envelope.SHA)
  if err!=nil||len(expected)!=32||!bytes.Equal(expected,actual[:]){return Pack{},errors.New("Studio policy digest mismatch")}
  return parsePack(envelope.Policy)
 },nil
}
func PackSourceFromProperties(properties map[string]string,internal Pack)(PackSource,error){
 switch properties["qualityrag.packspec.source"]{
 case "internal":return InternalPackSource(internal)
 case "property":return PropertyPackSource(properties["qualityrag.packspec.json"])
 case "file":return FilePackSource(properties["qualityrag.packspec.path"])
 case "studio":return StudioPackSource(properties["qualityrag.registry.url"],properties["qualityrag.registry.token"],properties["qualityrag.service-id"],properties["qualityrag.environment"],nil)
 default:return nil,errors.New("explicit PackSpec source required")
 }
}
