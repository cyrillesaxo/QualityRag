<?php
require __DIR__.'/src/QualityRag.php';
use QualityRag\Gate;
$pack=['id'=>'p','version'=>'1','requirements'=>[['id'=>'r','min_independent_sources'=>2]]];
$now=new DateTimeImmutable('2026-11-02T10:05:00Z');
$a=['id'=>'a','requirement_id'=>'r','origin'=>'A','source_ref'=>'doc:a','status'=>'SUPPORTS','observed_at'=>'2026-11-02T10:00:00Z'];
$b=array_merge($a,['id'=>'b','origin'=>'B']);
assert(Gate::evaluate($pack,[$a,$b],$now)['verdict']==='ADMIT');
assert(Gate::evaluate($pack,[$a,array_merge($b,['origin'=>'A'])],$now)['verdict']==='INCONCLUSIVE');
assert(Gate::evaluate($pack,[$a,array_merge($b,['status'=>'CONTRADICTS'])],$now)['verdict']==='REFUSE');
echo "PHP smoke passed\n";
