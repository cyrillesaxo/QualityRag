require "json"
require "digest"
require "net/http"
require "uri"
module QualityRag
 module Sources
  MAX_BYTES=262_144
  SEGMENT=/\A[A-Za-z0-9._-]+\z/
  def self.validate(pack)
   raise ArgumentError, "invalid PackSpec" unless pack.is_a?(Hash) &&
     pack["id"].is_a?(String) && !pack["id"].empty? &&
     pack["version"].is_a?(String) && !pack["version"].empty? &&
     pack["requirements"].is_a?(Array) && !pack["requirements"].empty?
   ids=[]
   pack["requirements"].each do |r|
     raise ArgumentError, "invalid requirement" unless r.is_a?(Hash)&&r["id"].is_a?(String)&&!r["id"].empty?&&!ids.include?(r["id"])
     ids << r["id"]
     {"min_independent_sources"=>1, "max_age_seconds"=>0}.each do |key,min|
       if r.key?(key) && (!r[key].is_a?(Integer)||r[key]<min)
         raise ArgumentError, "invalid threshold"
       end
     end
   end
   pack
  end
  def self.internal(pack)
   snapshot=JSON.generate(validate(pack))
   -> { validate(JSON.parse(snapshot)) }
  end
  def self.property(json)
   internal(validate(JSON.parse(json)))
  end
  def self.file(path)
   raise ArgumentError, "missing path" unless path.is_a?(String)&&!path.empty?
   -> {
     raise IOError, "policy file too large" if File.size(path)>MAX_BYTES
     validate(JSON.parse(File.read(path,encoding:"UTF-8")))
   }
  end
  def self.studio(base:,token:,service:,environment:,http_get:nil)
   uri=URI.parse(base)
   raise ArgumentError,"HTTPS required outside loopback" unless uri.scheme=="https"||
     (uri.scheme=="http"&&["localhost","127.0.0.1"].include?(uri.host))
   raise ArgumentError,"invalid registry URL" unless uri.userinfo.nil? && uri.query.nil? && uri.fragment.nil?
   raise ArgumentError,"invalid registry credential or identity" unless token.is_a?(String)&&!token.empty?&&
     SEGMENT.match?(service.to_s)&&SEGMENT.match?(environment.to_s)
   endpoint=URI.join(base.end_with?("/") ? base : base+"/", "/v1/resolve/#{service}/#{environment}")
   loader=http_get || lambda { |address,key|
     request=Net::HTTP::Get.new(address)
     request["Authorization"]="Bearer #{key}"
     response=Net::HTTP.start(address.host,address.port,use_ssl:address.scheme=="https",
       open_timeout:3,read_timeout:5) { |http| http.request(request) }
     raise IOError,"Studio resolution failed" unless response.is_a?(Net::HTTPSuccess)
     response.body
   }
   -> {
     raw=loader.call(endpoint,token)
     raise IOError,"invalid Studio response" unless raw.is_a?(String)&&raw.bytesize<=MAX_BYTES
     envelope=JSON.parse(raw)
     raise IOError,"Studio binding mismatch" unless envelope["status"]=="APPROVED"&&
       envelope["serviceId"]==service&&envelope["environment"]==environment
     pack=validate(envelope["policy"])
     digest=envelope["sha256"]
     actual=Digest::SHA256.hexdigest(JSON.generate(pack))
     raise IOError,"Studio digest mismatch" unless digest.is_a?(String)&&
       /\A[0-9a-f]{64}\z/.match?(digest)&&digest==actual
     pack
   }
  end
  def self.from_properties(props,internal_pack:nil)
   case props["qualityrag.packspec.source"]
   when "internal" then internal(internal_pack)
   when "property" then property(props.fetch("qualityrag.packspec.json"))
   when "file" then file(props.fetch("qualityrag.packspec.path"))
   when "studio" then studio(base:props.fetch("qualityrag.registry.url"),
     token:props.fetch("qualityrag.registry.token"),service:props.fetch("qualityrag.service-id"),
     environment:props.fetch("qualityrag.environment"))
   else raise ArgumentError,"explicit PackSpec source required"
   end
  end
 end
end
