import Foundation
import CryptoKit

/// Source policies are explicitly selected. No implicit fallback on error.
public enum PackSpecSources {
    public typealias Loader = () async throws -> Pack
    public enum SourceError: Error { case invalidPolicy, missingConfiguration, insecureRegistry, invalidBinding, invalidDigest, oversized }
    private static func parse(_ data: Data) throws -> Pack {
        guard let root = try JSONSerialization.jsonObject(with:data) as? [String:Any],
              let id = root["id"] as? String, !id.isEmpty,
              let version = root["version"] as? String, !version.isEmpty,
              let rows = root["requirements"] as? [[String:Any]], !rows.isEmpty else {
            throw SourceError.invalidPolicy
        }
        var ids=Set<String>()
        let requirements=try rows.map { row -> Requirement in
            guard let name=row["id"] as? String, !name.isEmpty, ids.insert(name).inserted else {
                throw SourceError.invalidPolicy
            }
            let min=row["min_independent_sources"] as? Int ?? 1
            let max=row["max_age_seconds"] as? Int
            guard min>0 && (max == nil || max! >= 0) else {throw SourceError.invalidPolicy}
            return Requirement(name,minIndependentSources:min,maxAgeSeconds:max.map(TimeInterval.init))
        }
        return Pack(id,version,requirements)
    }
    public static func internalPolicy(_ policy:Pack) throws -> Loader {
        guard !policy.id.isEmpty && !policy.version.isEmpty && !policy.requirements.isEmpty &&
          Set(policy.requirements.map{$0.id}).count==policy.requirements.count &&
          policy.requirements.allSatisfy({!$0.id.isEmpty && $0.minIndependentSources>0 &&
            ($0.maxAgeSeconds == nil || $0.maxAgeSeconds! >= 0)}) else {throw SourceError.invalidPolicy}
        return { policy }
    }
    public static func property(_ json:String) throws -> Loader {
        let pack=try parse(Data(json.utf8))
        return try internalPolicy(pack)
    }
    public static func file(_ url:URL) -> Loader {
        return {
            guard url.isFileURL else {throw SourceError.invalidPolicy}
            let attrs=try FileManager.default.attributesOfItem(atPath:url.path)
            let size=(attrs[.size] as? NSNumber)?.intValue ?? 262145
            guard size <= 262144 else {throw SourceError.oversized}
            return try parse(Data(contentsOf:url))
        }
    }
    /// Bytes of the nested policy object, extracted without reordering JSON keys.
    private static func rawPolicy(_ data:Data) throws -> Data {
        let bytes=Array(data)
        let key=Array("\"policy\"".utf8)
        guard bytes.count>=key.count else {throw SourceError.invalidPolicy}
        var start:Int?=nil
        for i in 0...(bytes.count-key.count) where Array(bytes[i..<(i+key.count)])==key {
            var j=i+key.count
            while j<bytes.count && [UInt8(32),9,10,13].contains(bytes[j]) {j+=1}
            guard j<bytes.count && bytes[j]==58 else {continue}
            j+=1
            while j<bytes.count && [UInt8(32),9,10,13].contains(bytes[j]) {j+=1}
            if j<bytes.count && bytes[j]==123 {start=j;break}
        }
        guard let begin=start else {throw SourceError.invalidPolicy}
        var depth=0;var quoted=false;var escaped=false
        for j in begin..<bytes.count {
            let b=bytes[j]
            if quoted {
                if escaped {escaped=false}
                else if b==92 {escaped=true}
                else if b==34 {quoted=false}
            } else {
                if b==34 {quoted=true}
                else if b==123 {depth+=1}
                else if b==125 {
                    depth-=1
                    if depth==0 {return Data(bytes[begin...j])}
                }
            }
        }
        throw SourceError.invalidPolicy
    }
    public static func studio(base:URL,token:String,service:String,environment:String,
       session:URLSession = .shared) throws -> Loader {
        guard let parts=URLComponents(url:base,resolvingAgainstBaseURL:false),
          parts.scheme=="https" ||
          (parts.scheme=="http" && ["localhost","127.0.0.1"].contains(parts.host ?? "")),
          parts.user==nil,parts.password==nil,parts.query==nil,parts.fragment==nil else {
            throw SourceError.insecureRegistry
        }
        let pattern="^[A-Za-z0-9._-]+$"
        guard !token.isEmpty,service.range(of:pattern,options:.regularExpression) != nil,
          environment.range(of:pattern,options:.regularExpression) != nil else {throw SourceError.missingConfiguration}
        let endpoint=URL(string:"/v1/resolve/\(service)/\(environment)",relativeTo:base)!.absoluteURL
        return {
            var request=URLRequest(url:endpoint);request.timeoutInterval=5
            request.setValue("Bearer \(token)",forHTTPHeaderField:"Authorization")
            let (data,response)=try await session.data(for:request)
            guard (response as? HTTPURLResponse)?.statusCode==200,
                  data.count<=262144 else {throw SourceError.invalidBinding}
            guard let envelope=try JSONSerialization.jsonObject(with:data) as? [String:Any],
              envelope["status"] as? String=="APPROVED",
              envelope["serviceId"] as? String==service,
              envelope["environment"] as? String==environment,
              let expected=envelope["sha256"] as? String,
              expected.count==64,
              expected.range(of:"^[a-f0-9]{64}$",options:.regularExpression) != nil else {
                throw SourceError.invalidBinding
            }
            let raw=try rawPolicy(data)
            let digest=SHA256.hash(data:raw).map{String(format:"%02x",$0)}.joined()
            guard digest==expected else {throw SourceError.invalidDigest}
            return try parse(raw)
        }
    }
}
