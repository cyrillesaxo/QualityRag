<?php
declare(strict_types=1);
require __DIR__.'/src/PackSpecSource.php';
use QualityRag\PackSpecSource;
$pack=['id'=>'eu','version'=>'1','requirements'=>[['id'=>'general'],['id'=>'control']]];
$load=PackSpecSource::internal($pack);
$pack['id']='tampered';
assert($load()['id']==='eu');
$file=tempnam(sys_get_temp_dir(),'qr');
file_put_contents($file,json_encode($load()));
try {
    assert(PackSpecSource::file($file)()['id']==='eu');
    file_put_contents($file,'{}');
    try { PackSpecSource::file($file)(); throw new Exception('invalid policy admitted'); }
    catch(InvalidArgumentException $ok){}
}finally{unlink($file);}
$approved=$load();
$digest=hash('sha256',json_encode($approved,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE));
$envelope=['serviceId'=>'app','environment'=>'dev','status'=>'APPROVED','policy'=>$approved,'sha256'=>$digest];
$read=static fn()=>json_encode($envelope);
assert(PackSpecSource::studio('http://127.0.0.1:5055','token','app','dev',$read)()['id']==='eu');
$envelope['sha256']=str_repeat('0',64);
try { PackSpecSource::studio('http://127.0.0.1:5055','token','app','dev',$read)(); throw new Exception('tampered policy admitted'); }
catch(RuntimeException $ok){}
echo "PackSpec sources pass\n";
