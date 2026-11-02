<?php
declare(strict_types=1);
namespace QualityRag;
use DateTimeImmutable;
use InvalidArgumentException;

final class Gate {
    /** Evaluates caller-provided metadata, not source authenticity. */
    public static function evaluate(array $pack,array $evidence,?DateTimeImmutable $asOf=null):array {
        if (empty($pack['id']) || empty($pack['version']) || empty($pack['requirements']) || !is_array($pack['requirements'])) throw new InvalidArgumentException('invalid pack');
        $asOf ??= new DateTimeImmutable('now');
        $seen=[]; $findings=[];
        foreach($pack['requirements'] as $r) {
            $id=$r['id']??'';
            if (!is_string($id)||$id===''||isset($seen[$id])) throw new InvalidArgumentException('invalid requirement');
            $seen[$id]=true;
            $min=$r['min_independent_sources']??1;$max=$r['max_age_seconds']??null;
            if (!is_int($min)||$min<1||($max!==null&&(!is_int($max)||$max<0))) throw new InvalidArgumentException('invalid threshold');
            $origins=[];$reasons=[];$contradiction=false;
            foreach($evidence as $w) {
                if (($w['requirement_id']??null)!==$id) continue;
                $valid=true;
                foreach(['id','origin','source_ref','observed_at'] as $key) if (!isset($w[$key])||!is_string($w[$key])||$w[$key]==='') $valid=false;
                if (!$valid||!in_array($w['status']??null,['SUPPORTS','CONTRADICTS','UNKNOWN'],true)) {$reasons['INVALID_EVIDENCE']=true;continue;}
                try { $observed=new DateTimeImmutable($w['observed_at']); } catch (\Exception $e) {$reasons['INVALID_EVIDENCE']=true;continue;}
                $age=(float)$asOf->format('U.u')-(float)$observed->format('U.u');
                if ($age<0) {$reasons['FUTURE_EVIDENCE']=true;continue;}
                if ($max!==null&&$age>$max) {$reasons['STALE_EVIDENCE']=true;continue;}
                if ($w['status']==='CONTRADICTS') $contradiction=true;
                elseif($w['status']==='SUPPORTS') $origins[$w['origin']]=true;
                else $reasons['UNKNOWN_EVIDENCE']=true;
            }
            $count=count($origins);
            $verdict=$contradiction?'REFUSE':($count<$min?'INCONCLUSIVE':'ADMIT');
            if($contradiction)$reasons['CONTRADICTION']=true;
            elseif($count<$min)$reasons['INSUFFICIENT_INDEPENDENT_EVIDENCE']=true;
            $why=array_keys($reasons);sort($why);
            $findings[]=['requirement_id'=>$id,'verdict'=>$verdict,'independent_sources'=>$count,'reasons'=>$why];
        }
        $verdict='ADMIT';
        foreach($findings as $f){if($f['verdict']==='REFUSE'){$verdict='REFUSE';break;}if($f['verdict']==='INCONCLUSIVE')$verdict='INCONCLUSIVE';}
        return ['schema'=>'qualityrag.result/v0.1','pack_id'=>$pack['id'],'pack_version'=>$pack['version'],'verdict'=>$verdict,'findings'=>$findings];
    }
}
