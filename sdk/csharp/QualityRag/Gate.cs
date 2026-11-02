namespace QualityRag;
public record Requirement(string Id,int MinIndependentSources=1,long? MaxAgeSeconds=null);
public record Pack(string Id,string Version,IReadOnlyList<Requirement> Requirements);
public record Witness(string Id,string RequirementId,string Origin,string SourceRef,string Status,DateTimeOffset ObservedAt);
public record Finding(string RequirementId,string Verdict,int IndependentSources,IReadOnlyList<string> Reasons);
public record Result(string Schema,string PackId,string PackVersion,string Verdict,IReadOnlyList<Finding> Findings);
public static class Gate {
    // Checks claimed metadata; never establishes source authenticity.
    public static Result Evaluate(Pack pack,IReadOnlyList<Witness> evidence,DateTimeOffset now) {
        if(string.IsNullOrWhiteSpace(pack.Id)||string.IsNullOrWhiteSpace(pack.Version)||pack.Requirements is null||pack.Requirements.Count==0||evidence is null) throw new ArgumentException("Invalid inputs");
        if(pack.Requirements.Any(r=>string.IsNullOrWhiteSpace(r.Id)||r.MinIndependentSources<1||r.MaxAgeSeconds<0)||pack.Requirements.Select(r=>r.Id).Distinct().Count()!=pack.Requirements.Count) throw new ArgumentException("Invalid requirements");
        var findings=new List<Finding>();
        foreach(var r in pack.Requirements) {
            var origins=new HashSet<string>(); var reasons=new SortedSet<string>(); bool contradicted=false;
            foreach(var w in evidence.Where(w=>w.RequirementId==r.Id)) {
                if(string.IsNullOrWhiteSpace(w.Id)||string.IsNullOrWhiteSpace(w.Origin)||string.IsNullOrWhiteSpace(w.SourceRef)||!new[]{"SUPPORTS","CONTRADICTS","UNKNOWN"}.Contains(w.Status)){reasons.Add("INVALID_EVIDENCE");continue;}
                var age=now-w.ObservedAt;
                if(age<TimeSpan.Zero){reasons.Add("FUTURE_EVIDENCE");continue;}
                if(r.MaxAgeSeconds is long max && age>TimeSpan.FromSeconds(max)){reasons.Add("STALE_EVIDENCE");continue;}
                if(w.Status=="CONTRADICTS") contradicted=true;
                else if(w.Status=="SUPPORTS") origins.Add(w.Origin);
                else reasons.Add("UNKNOWN_EVIDENCE");
            }
            var verdict=contradicted?"REFUSE":origins.Count<r.MinIndependentSources?"INCONCLUSIVE":"ADMIT";
            if(contradicted)reasons.Add("CONTRADICTION");
            else if(origins.Count<r.MinIndependentSources)reasons.Add("INSUFFICIENT_INDEPENDENT_EVIDENCE");
            findings.Add(new(r.Id,verdict,origins.Count,reasons.ToList()));
        }
        var decision=findings.Any(f=>f.Verdict=="REFUSE")?"REFUSE":findings.Any(f=>f.Verdict=="INCONCLUSIVE")?"INCONCLUSIVE":"ADMIT";
        return new("qualityrag.result/v0.1",pack.Id,pack.Version,decision,findings);
    }
}
