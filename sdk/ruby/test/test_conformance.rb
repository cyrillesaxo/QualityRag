require "json"
require "minitest/autorun"
require_relative "../lib/qualityrag"
class ConformanceTest < Minitest::Test
 def test_shared_fixtures
  suite=JSON.parse(File.read(File.expand_path("../../../conformance/v0.1.json",__dir__)))
  suite["cases"].each do |c|
   evidence=c["evidence"].map do |row|
    {"id"=>row[0],"origin"=>row[1],"status"=>row[2],"requirement_id"=>"r","source_ref"=>"doc:"+row[0],"observed_at"=>row[3]||"2026-11-02T10:00:00Z"}
   end
   result=QualityRag.evaluate(suite["pack"],evidence,as_of:Time.iso8601(suite["as_of"]))
   assert_equal c["verdict"],result["verdict"],c["name"]
   assert_equal c["reasons"],result["findings"][0]["reasons"],c["name"]
  end
 end
end
