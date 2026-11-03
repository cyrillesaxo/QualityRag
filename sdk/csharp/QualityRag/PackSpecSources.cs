using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace QualityRag;

/// <summary>One policy authority per deployment. Never fall back after resolution errors.</summary>
public static class PackSpecSources {
    public delegate Task<Pack> Loader(CancellationToken cancellation = default);
    private static Pack Parse(string json) {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        if(root.ValueKind != JsonValueKind.Object) throw new ArgumentException("Invalid PackSpec");
        string id = root.GetProperty("id").GetString() ?? "";
        string version = root.GetProperty("version").GetString() ?? "";
        var items = root.GetProperty("requirements");
        if(string.IsNullOrWhiteSpace(id) || string.IsNullOrWhiteSpace(version) ||
           items.ValueKind != JsonValueKind.Array || items.GetArrayLength() == 0) throw new ArgumentException("Invalid PackSpec");
        var reqs = new List<Requirement>(); var seen = new HashSet<string>();
        foreach(var row in items.EnumerateArray()) {
            var name = row.GetProperty("id").GetString() ?? "";
            if(string.IsNullOrWhiteSpace(name) || !seen.Add(name)) throw new ArgumentException("Invalid requirement");
            int minimum = row.TryGetProperty("min_independent_sources", out var min) ? min.GetInt32() : 1;
            long? max = row.TryGetProperty("max_age_seconds", out var age) ? age.GetInt64() : null;
            if(minimum < 1 || max < 0) throw new ArgumentException("Invalid threshold");
            reqs.Add(new Requirement(name, minimum, max));
        }
        return new Pack(id, version, reqs);
    }
    private static string Snapshot(Pack pack) {
        if(string.IsNullOrWhiteSpace(pack.Id) || string.IsNullOrWhiteSpace(pack.Version) ||
           pack.Requirements.Count == 0 || pack.Requirements.Any(x=>string.IsNullOrWhiteSpace(x.Id)||x.MinIndependentSources<1||x.MaxAgeSeconds<0) ||
           pack.Requirements.Select(x=>x.Id).Distinct().Count()!=pack.Requirements.Count) throw new ArgumentException("Invalid PackSpec");
        return JsonSerializer.Serialize(pack);
    }
    public static Loader Internal(Pack pack) {
        string snapshot=Snapshot(pack);
        return _ => Task.FromResult(JsonSerializer.Deserialize<Pack>(snapshot)!);
    }
    public static Loader Property(string json) {
        var pack=Parse(json);
        return Internal(pack);
    }
    public static Loader File(string path) {
        if(string.IsNullOrWhiteSpace(path)) throw new ArgumentException("Missing policy path");
        return async ct => {
            var info = new FileInfo(path);
            if(info.Length > 262144) throw new InvalidDataException("Policy file too large");
            return Parse(await System.IO.File.ReadAllTextAsync(path, ct));
        };
    }
    public static Loader Studio(Uri baseUri, string token, string serviceId, string environment, HttpClient? client=null) {
        if(!baseUri.IsAbsoluteUri ||
           !(baseUri.Scheme=="https" || (baseUri.Scheme=="http" && (baseUri.Host=="localhost" || baseUri.Host=="127.0.0.1"))) ||
           !string.IsNullOrEmpty(baseUri.UserInfo) || !string.IsNullOrEmpty(baseUri.Query) || !string.IsNullOrEmpty(baseUri.Fragment))
            throw new ArgumentException("HTTPS required outside loopback");
        if(string.IsNullOrWhiteSpace(token) ||
           !System.Text.RegularExpressions.Regex.IsMatch(serviceId??"", "^[A-Za-z0-9._-]+$") ||
           !System.Text.RegularExpressions.Regex.IsMatch(environment??"", "^[A-Za-z0-9._-]+$")) throw new ArgumentException("Invalid Studio configuration");
        var http=client??new HttpClient{Timeout=TimeSpan.FromSeconds(5)};
        var endpoint=new Uri(baseUri, "/v1/resolve/"+serviceId+"/"+environment);
        return async ct => {
            using var request=new HttpRequestMessage(HttpMethod.Get, endpoint);
            request.Headers.Authorization=new AuthenticationHeaderValue("Bearer",token);
            using var response=await http.SendAsync(request,ct);
            response.EnsureSuccessStatusCode();
            var body=await response.Content.ReadAsStringAsync(ct);
            if(Encoding.UTF8.GetByteCount(body)>262144)throw new InvalidDataException("Studio response too large");
            using var doc=JsonDocument.Parse(body);
            var root=doc.RootElement;
            if(root.GetProperty("status").GetString()!="APPROVED" ||
               root.GetProperty("serviceId").GetString()!=serviceId ||
               root.GetProperty("environment").GetString()!=environment)throw new InvalidDataException("Studio binding mismatch");
            var policy=root.GetProperty("policy");
            string expected=root.GetProperty("sha256").GetString()??"";
            string actual=Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(policy)))).ToLowerInvariant();
            if(!System.Text.RegularExpressions.Regex.IsMatch(expected,"^[0-9a-f]{64}$") ||
               !CryptographicOperations.FixedTimeEquals(Encoding.ASCII.GetBytes(expected),Encoding.ASCII.GetBytes(actual)))
                throw new InvalidDataException("Studio policy digest mismatch");
            return Parse(policy.GetRawText());
        };
    }
    public static Loader FromProperties(IReadOnlyDictionary<string,string> config, Pack? embedded=null) {
        string Read(string key) => config.TryGetValue(key,out var value) && !string.IsNullOrWhiteSpace(value)
            ? value : throw new ArgumentException("Missing " + key);
        return Read("qualityrag.packspec.source") switch {
            "internal" => Internal(embedded??throw new ArgumentException("Internal policy absent")),
            "property" => Property(Read("qualityrag.packspec.json")),
            "file" => File(Read("qualityrag.packspec.path")),
            "studio" => Studio(new Uri(Read("qualityrag.registry.url")), Read("qualityrag.registry.token"),
                Read("qualityrag.service-id"), Read("qualityrag.environment")),
            _ => throw new ArgumentException("Unknown PackSpec source")
        };
    }
}
