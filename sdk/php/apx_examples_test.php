<?php
declare(strict_types=1);
require __DIR__.'/src/QualityRag.php';
$fixture=json_decode(file_get_contents(__DIR__.'/../../examples/apx-packspecs/fixtures.json'),true,512,JSON_THROW_ON_ERROR);
$count=0;
foreach($fixture['scenarios'] as $domain){
 foreach($domain['cases'] as $example){
  $out=\QualityRag\Gate::evaluate($domain['pack'],$example['evidence'],new DateTimeImmutable($fixture['as_of']));
  if($out['verdict']!==$example['expected'])throw new RuntimeException($domain['id'].'/'.$example['id']);
  $count++;
 }
}
if($count!==15)throw new RuntimeException('Missing examples');
echo "PHP 15 APX derived cases passed\n";
