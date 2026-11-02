<?php
require __DIR__.'/src/QualityRag.php';
use QualityRag\Gate;
$suite=json_decode(file_get_contents(__DIR__.'/../../conformance/v0.1.json'),true,512,JSON_THROW_ON_ERROR);
foreach($suite['cases'] as $case){
 $evidence=array_map(static function(array $r):array {
  return ['id'=>$r[0],'origin'=>$r[1],'status'=>$r[2],'requirement_id'=>'r','source_ref'=>'doc:'.$r[0],'observed_at'=>$r[3]??'2026-11-02T10:00:00Z'];
 },$case['evidence']);
 $out=Gate::evaluate($suite['pack'],$evidence,new DateTimeImmutable($suite['as_of']));
 if($out['verdict']!==$case['verdict']||$out['findings'][0]['reasons']!==$case['reasons'])throw new RuntimeException('Conformance mismatch: '.$case['name']);
}
echo "PHP shared conformance passed\n";
