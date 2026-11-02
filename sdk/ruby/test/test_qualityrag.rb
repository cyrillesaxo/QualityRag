require "minitest/autorun"
require_relative "../lib/qualityrag"
class QualityRagTest < Minitest::Test
  def setup
    @pack = {"id"=>"demo","version"=>"1","requirements"=>[{"id"=>"r","min_independent_sources"=>2}]}
    @now = Time.iso8601("2026-11-02T10:05:00Z")
  end
  def witness(id,origin,status="SUPPORTS")
    {"id"=>id,"origin"=>origin,"requirement_id"=>"r","source_ref"=>"doc:"+id,"status"=>status,"observed_at"=>"2026-11-02T10:00:00Z"}
  end
  def test_three_decisions
    a=witness("a","A"); b=witness("b","B")
    assert_equal "ADMIT", QualityRag.evaluate(@pack,[a,b],as_of:@now)["verdict"]
    assert_equal "INCONCLUSIVE", QualityRag.evaluate(@pack,[a,b.merge("origin"=>"A")],as_of:@now)["verdict"]
    assert_equal "REFUSE", QualityRag.evaluate(@pack,[a,b.merge("status"=>"CONTRADICTS")],as_of:@now)["verdict"]
  end
end
