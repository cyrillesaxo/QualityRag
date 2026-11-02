require "time"
module QualityRag
  def self.evaluate(pack, evidence, as_of: Time.now.utc)
    raise ArgumentError, "invalid pack" unless pack.is_a?(Hash) && pack["id"].to_s != "" && pack["version"].to_s != "" && pack["requirements"].is_a?(Array) && !pack["requirements"].empty? && evidence.is_a?(Array)
    ids = pack["requirements"].map { |r| r["id"] }
    raise ArgumentError, "invalid requirements" if ids.any? { |x| x.to_s.empty? } || ids.uniq.size != ids.size
    findings = pack["requirements"].map do |r|
      min = r.fetch("min_independent_sources", 1)
      max = r["max_age_seconds"]
      raise ArgumentError, "bad threshold" unless min.is_a?(Integer) && min >= 1 && (max.nil? || (max.is_a?(Integer) && max >= 0))
      origins = []; reasons = []; contradiction = false
      evidence.select { |w| w["requirement_id"] == r["id"] }.each do |w|
        unless %w[id origin source_ref observed_at].all? { |k| w[k].is_a?(String) && !w[k].empty? } && %w[SUPPORTS CONTRADICTS UNKNOWN].include?(w["status"])
          reasons << "INVALID_EVIDENCE"; next
        end
        begin
          observed = Time.iso8601(w["observed_at"])
        rescue ArgumentError
          reasons << "INVALID_EVIDENCE"; next
        end
        age = as_of - observed
        if age < 0
          reasons << "FUTURE_EVIDENCE"
        elsif max && age > max
          reasons << "STALE_EVIDENCE"
        elsif w["status"] == "CONTRADICTS"
          contradiction = true
        elsif w["status"] == "SUPPORTS"
          origins << w["origin"]
        else
          reasons << "UNKNOWN_EVIDENCE"
        end
      end
      count = origins.uniq.size
      verdict = contradiction ? "REFUSE" : count < min ? "INCONCLUSIVE" : "ADMIT"
      reasons << "CONTRADICTION" if contradiction
      reasons << "INSUFFICIENT_INDEPENDENT_EVIDENCE" if !contradiction && count < min
      {"requirement_id"=>r["id"],"verdict"=>verdict,"independent_sources"=>count,"reasons"=>reasons.uniq.sort}
    end
    verdict = findings.any? { |f| f["verdict"] == "REFUSE" } ? "REFUSE" : findings.any? { |f| f["verdict"] == "INCONCLUSIVE" } ? "INCONCLUSIVE" : "ADMIT"
    {"schema"=>"qualityrag.result/v0.1","pack_id"=>pack["id"],"pack_version"=>pack["version"],"verdict"=>verdict,"findings"=>findings}
  end
end
