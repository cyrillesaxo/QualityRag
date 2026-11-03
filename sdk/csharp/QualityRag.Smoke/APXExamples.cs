using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using QualityRag;
public static class APXExamples {
 public static void Check() {
  using var doc=JsonDocument.Parse(File.ReadAllText("examples/apx-packspecs/fixtures.json"));
  var fixture=doc.RootElement;
  var at=DateTimeOffset.Parse(fixture.GetProperty("as_of").GetString()!);
  int count=0;
  foreach(var domain in fixture.GetProperty("scenarios").EnumerateArray()){
   var raw=domain.GetProperty("pack");
   var pack=new Pack(raw.GetProperty("id").GetString()!,raw.GetProperty("version").GetString()!,
    raw.GetProperty("requirements").EnumerateArray().Select(r=>new Requirement(r.GetProperty("id").GetString()!)).ToArray());
   foreach(var example in domain.GetProperty("cases").EnumerateArray()){
    var rows=example.GetProperty("evidence").EnumerateArray().Select(w=>new Witness(
     w.GetProperty("id").GetString()!,w.GetProperty("requirement_id").GetString()!,
     w.GetProperty("origin").GetString()!,w.GetProperty("source_ref").GetString()!,
     w.GetProperty("status").GetString()!,DateTimeOffset.Parse(w.GetProperty("observed_at").GetString()!))).ToArray();
    var result=Gate.Evaluate(pack,rows,at);
    if(result.Verdict!=example.GetProperty("expected").GetString())throw new Exception("APX fixture mismatch");
    count++;
   }
  }
  if(count!=12)throw new Exception("Missing APX cases");
 }
}
