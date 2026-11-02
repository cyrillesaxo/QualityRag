using System.Text.Json;
using QualityRag;
public static class Conformance {
 public static void Run() {
  var path=Path.GetFullPath("conformance/v0.1.json");
  using var doc=JsonDocument.Parse(File.ReadAllText(path));
  var root=doc.RootElement;
  var now=DateTimeOffset.Parse(root.GetProperty("as_of").GetString()!);
  var p=new Pack("conformance","1",new[]{new Requirement("r",2,3600)});
  foreach(var c in root.GetProperty("cases").EnumerateArray()){
   var rows=new List<Witness>();
   foreach(var row in c.GetProperty("evidence").EnumerateArray()){
    var values=row.EnumerateArray().Select(x=>x.GetString()!).ToArray();
    var at=values.Length>3?values[3]:"2026-11-02T10:00:00Z";
    rows.Add(new Witness(values[0],"r",values[1],"doc:"+values[0],values[2],DateTimeOffset.Parse(at)));
   }
   var result=Gate.Evaluate(p,rows,now);
   var expected=c.GetProperty("verdict").GetString();
   if(result.Verdict!=expected)throw new Exception("Conformance verdict mismatch: "+c.GetProperty("name").GetString());
   var reasons=c.GetProperty("reasons").EnumerateArray().Select(x=>x.GetString()!).ToArray();
   if(!result.Findings[0].Reasons.SequenceEqual(reasons))throw new Exception("Conformance reason mismatch: "+c.GetProperty("name").GetString());
  }
 }
}
