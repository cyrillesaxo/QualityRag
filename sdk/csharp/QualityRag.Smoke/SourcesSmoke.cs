using System;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using QualityRag;

public static class SourcesSmoke {
    public static async Task Check() {
        var pack = new Pack("eu", "1", new List<Requirement>{new("general"),new("control")});
        var internalLoad = PackSpecSources.Internal(pack);
        if((await internalLoad()).Id != "eu") throw new Exception("Internal source failed");
        var inline = PackSpecSources.Property("{\"id\":\"eu\",\"version\":\"1\",\"requirements\":[{\"id\":\"general\"},{\"id\":\"control\"}]}");
        if((await inline()).Requirements.Count != 2) throw new Exception("Property source failed");
        string path=Path.GetTempFileName();
        try {
            await File.WriteAllTextAsync(path,"{}");
            var load=PackSpecSources.File(path);
            try { await load(); throw new Exception("Invalid policy admitted"); }
            catch(ArgumentException) {}
        } finally { File.Delete(path); }
        try { PackSpecSources.Studio(new Uri("http://example.com"),"token","app","dev"); throw new Exception("Insecure URL accepted"); }
        catch(ArgumentException) {}
    }
}
