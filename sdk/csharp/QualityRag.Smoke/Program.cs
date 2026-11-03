using QualityRag;
var now=new DateTimeOffset(2026,11,2,10,5,0,TimeSpan.Zero);
var p=new Pack("p","1",new[]{new Requirement("r",2,3600)});
var a=new Witness("a","r","A","doc:a","SUPPORTS",now.AddMinutes(-5));
var b=new Witness("b","r","B","doc:b","SUPPORTS",now.AddMinutes(-5));
if(Gate.Evaluate(p,new[]{a,b},now).Verdict!="ADMIT")throw new Exception("Expected ADMIT");
if(Gate.Evaluate(p,new[]{a,b with{Origin="A"}},now).Verdict!="INCONCLUSIVE")throw new Exception("Expected INCONCLUSIVE");
if(Gate.Evaluate(p,new[]{a,b with{Status="CONTRADICTS"}},now).Verdict!="REFUSE")throw new Exception("Expected REFUSE");
Console.WriteLine("QualityRag .NET smoke passed");

Conformance.Run();

await SourcesSmoke.Check();
