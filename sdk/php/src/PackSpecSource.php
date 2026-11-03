<?php
declare(strict_types=1);
namespace QualityRag;

/** Explicit authority selection; failed Studio resolution never falls back. */
final class PackSpecSource {
    private const MAX = 262144;
    private static function validate(mixed $pack): array {
        if (!is_array($pack) || !is_string($pack['id']??null) || trim($pack['id'])==='' ||
            !is_string($pack['version']??null) || trim($pack['version'])==='' ||
            !is_array($pack['requirements']??null) || count($pack['requirements'])===0)
            throw new \InvalidArgumentException('Invalid PackSpec');
        $seen=[];
        foreach($pack['requirements'] as $req) {
            $id=$req['id']??null;
            if(!is_string($id)||$id===''||isset($seen[$id]))throw new \InvalidArgumentException('Invalid requirement');
            $seen[$id]=true;
            foreach(['min_independent_sources'=>1,'max_age_seconds'=>0] as $key=>$min)
                if(array_key_exists($key,$req)&&(!is_int($req[$key])||$req[$key]<$min))
                    throw new \InvalidArgumentException('Invalid threshold');
        }
        return $pack;
    }
    private static function parse(string $json): array {
        return self::validate(json_decode($json,true,512,JSON_THROW_ON_ERROR));
    }
    public static function internal(array $pack): \Closure {
        $snapshot=json_encode(self::validate($pack),JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);
        return static fn():array=>self::parse($snapshot);
    }
    public static function property(string $json): \Closure {
        return self::internal(self::parse($json));
    }
    public static function file(string $path): \Closure {
        if(trim($path)==='')throw new \InvalidArgumentException('Missing policy file');
        return static function()use($path):array {
            if(!is_file($path)||filesize($path)>self::MAX)throw new \RuntimeException('Policy unavailable or too large');
            $json=file_get_contents($path);
            if($json===false)throw new \RuntimeException('Policy read failed');
            return self::parse($json);
        };
    }
    /** Local dev registry only. Caller may inject HTTP adapter for testing. */
    public static function studio(string $base,string $token,string $service,string $environment,?callable $get=null):\Closure {
        $parts=parse_url($base);
        if(!is_array($parts)||isset($parts['user'])||isset($parts['pass'])||
            isset($parts['query'])||isset($parts['fragment']))throw new \InvalidArgumentException('Invalid URL');
        $scheme=strtolower($parts['scheme']??'');$host=strtolower($parts['host']??'');
        if(!($scheme==='https'||($scheme==='http'&&in_array($host,['localhost','127.0.0.1'],true))))
            throw new \InvalidArgumentException('HTTPS required outside loopback');
        if(trim($token)===''||!preg_match('/^[A-Za-z0-9._-]+$/D',$service)||
            !preg_match('/^[A-Za-z0-9._-]+$/D',$environment))throw new \InvalidArgumentException('Invalid Studio configuration');
        $endpoint=rtrim($base,'/').'/v1/resolve/'.$service.'/'.$environment;
        $transport=$get??static function(string $url,string $token):string {
            $options=['http'=>['method'=>'GET','timeout'=>5,'ignore_errors'=>false,'header'=>"Authorization: Bearer ".$token."\r\nAccept: application/json\r\n"]];
            $body=@file_get_contents($url,false,stream_context_create($options),0,self::MAX+1);
            if($body===false)throw new \RuntimeException('Studio unavailable');
            return $body;
        };
        return static function()use($transport,$endpoint,$token,$service,$environment):array {
            $body=$transport($endpoint,$token);
            if(!is_string($body)||strlen($body)>self::MAX)throw new \RuntimeException('Invalid Studio response');
            $envelope=json_decode($body,true,512,JSON_THROW_ON_ERROR);
            if(($envelope['status']??'')!=='APPROVED'||($envelope['serviceId']??'')!==$service||
                ($envelope['environment']??'')!==$environment)throw new \RuntimeException('Studio binding mismatch');
            $pack=self::validate($envelope['policy']??null);
            $digest=$envelope['sha256']??'';
            // Matches registry JSON.stringify policy key order for ordinary JSON policies.
            $actual=hash('sha256',json_encode($pack,JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE));
            if(!is_string($digest)||!preg_match('/^[a-f0-9]{64}$/D',$digest)||!hash_equals($digest,$actual))
                throw new \RuntimeException('Studio digest mismatch');
            return $pack;
        };
    }
    public static function fromProperties(array $p,?array $internal=null):\Closure {
        return match($p['qualityrag.packspec.source']??null){
            'internal'=>self::internal($internal??[]),
            'property'=>self::property($p['qualityrag.packspec.json']??''),
            'file'=>self::file($p['qualityrag.packspec.path']??''),
            'studio'=>self::studio($p['qualityrag.registry.url']??'',$p['qualityrag.registry.token']??'',
                $p['qualityrag.service-id']??'',$p['qualityrag.environment']??''),
            default=>throw new \InvalidArgumentException('Explicit PackSpec source required')
        };
    }
}
