require "minitest/autorun"
require "tempfile"
require_relative "../lib/qualityrag/sources"

class SourceTests < Minitest::Test
 def setup
  @pack={"id"=>"eu","version"=>"1","requirements"=>[{"id"=>"general"},{"id"=>"control"}]}
 end
 def test_internal_and_file_fail_closed
  p=@pack.dup
  loader=QualityRag::Sources.internal(p)
  p["id"]="changed"
  assert_equal "eu",loader.call["id"]
  Tempfile.create("qualityrag") do |f|
   f.write(JSON.generate(@pack));f.flush
   loader=QualityRag::Sources.file(f.path)
   assert_equal "eu",loader.call["id"]
   File.write(f.path,"{}")
   assert_raises(ArgumentError) {loader.call}
  end
 end
 def test_studio_digest
  digest=Digest::SHA256.hexdigest(JSON.generate(@pack))
  envelope={"serviceId"=>"app","environment"=>"dev","status"=>"APPROVED","sha256"=>digest,"policy"=>@pack}
  loader=QualityRag::Sources.studio(base:"http://127.0.0.1:5055",token:"secret",service:"app",environment:"dev",
    http_get:->(_url,_token){JSON.generate(envelope)})
  assert_equal "eu",loader.call["id"]
  envelope["sha256"]="0"*64
  assert_raises(IOError) {loader.call}
  assert_raises(ArgumentError) {
   QualityRag::Sources.studio(base:"http://evil.example",token:"secret",service:"app",environment:"dev")
  }
 end
end
