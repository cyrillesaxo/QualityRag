require "minitest/autorun"
require "json"
require "time"
require_relative "../lib/qualityrag"
class APXExamplesTest < Minitest::Test
 def test_fifteen_cases
  fixture=JSON.parse(File.read(File.expand_path("../../../examples/apx-packspecs/fixtures.json",__dir__)))
  count=0
  fixture["scenarios"].each do |domain|
   domain["cases"].each do |example|
    result=QualityRag.evaluate(domain["pack"],example["evidence"],as_of:Time.iso8601(fixture["as_of"]))
    assert_equal example["expected"],result["verdict"],domain["id"]+"/"+example["id"]
    count+=1
   end
  end
  assert_equal 15,count
 end
end
