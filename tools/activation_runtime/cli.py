"""CLI for validation, external PackSpec evaluation, source fallback and local serving."""
import argparse
import json
from pathlib import Path
import sys

from .common import strict_json
from .contracts import validate
from .scene_codec import train_model,encode,decode
from .service import Application,server


def read(path,limit=524288):
    path=Path(path)
    if path.stat().st_size>limit:raise ValueError("Input file byte budget")
    return strict_json(path.read_bytes(),max_bytes=limit)


def main(argv=None):
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("validate");p.add_argument("schema");p.add_argument("file")
    p=sub.add_parser("evaluate");p.add_argument("--endpoint",required=True);p.add_argument("--token",required=True);p.add_argument("--request",required=True)
    p=sub.add_parser("activate-plan");p.add_argument("--endpoint",required=True);p.add_argument("--token",required=True);p.add_argument("--request",required=True);p.add_argument("--source")
    p=sub.add_parser("trace");p.add_argument("--endpoint",required=True);p.add_argument("--token",required=True);p.add_argument("--request",required=True)
    p=sub.add_parser("fallback");p.add_argument("--endpoint",required=True);p.add_argument("--token",required=True);p.add_argument("--source-sha256",required=True)
    p=sub.add_parser("observations");p.add_argument("--source",required=True);p.add_argument("--request",required=True)
    p=sub.add_parser("economics");p.add_argument("--request",required=True)
    p=sub.add_parser("train-scene");p.add_argument("--source",action="append",required=True);p.add_argument("--out",required=True)
    p=sub.add_parser("encode-scene");p.add_argument("--source",required=True);p.add_argument("--model",required=True);p.add_argument("--out",required=True)
    p=sub.add_parser("decode-scene");p.add_argument("--payload",required=True);p.add_argument("--model",required=True);p.add_argument("--out",required=True)
    p=sub.add_parser("serve");p.add_argument("--root",required=True);p.add_argument("--keys",required=True);p.add_argument("--port",type=int,default=8769)
    args=parser.parse_args(argv)
    if args.command=="validate":
        validate(args.schema,read(args.file));result={"valid":True,"semantic_admission":"INCONCLUSIVE"}
    elif args.command in {"evaluate","activate-plan","trace","fallback"}:
        sdk=str(Path(__file__).resolve().parents[2]/"sdk"/"python")
        if sdk not in sys.path:sys.path.insert(0,sdk)
        from qualityrag_activation import Client
        client=Client(args.endpoint,read(args.token))
        if args.command=="fallback":result=client.fallback(args.source_sha256)
        elif args.command=="activate-plan":
            if args.source:
                with Path(args.source).open("rb") as stream:raw=stream.read(65537)
                result=client.run_reviewed(raw,read(args.request))
            else:result=client.activate_plan(**read(args.request))
        elif args.command=="trace":result=client.trace(**read(args.request))
        else:result=client.evaluate(**read(args.request))
    elif args.command=="observations":
        from .semantic_ir import evaluate
        with Path(args.source).open("rb") as stream:raw=stream.read(65537)
        result=evaluate(raw,read(args.request))
    elif args.command=="economics":
        from .economics import catalog_uncertainty
        specification=read(args.request)
        if not isinstance(specification,dict) or set(specification)!={"groups","catalog_sizes","cohorts"}:
            raise ValueError("Complete catalog uncertainty request required")
        result=catalog_uncertainty(**specification)
    elif args.command=="train-scene":
        result=train_model(args.source);Path(args.out).write_text(json.dumps(result,sort_keys=True))
    elif args.command=="encode-scene":
        payload,result=encode(args.source,read(args.model));Path(args.out).write_text(json.dumps(payload,sort_keys=True))
    elif args.command=="decode-scene":result=decode(read(args.payload,40_000_000),read(args.model),args.out)
    else:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        import base64
        config=read(args.keys)
        keys=lambda name:{kid:Ed25519PublicKey.from_public_bytes(base64.b64decode(v,validate=True)) for kid,v in config[name].items()}
        authorities={}
        for tenant,row in config.get("preservation",{}).items():
            decode_keys=lambda values:{kid:Ed25519PublicKey.from_public_bytes(base64.b64decode(value,validate=True)) for kid,value in values.items()}
            authorities[tenant]={"review":decode_keys(row["review"]),"subjects":row["subjects"],"authors":decode_keys(row["authors"])}
        app=Application(args.root,access_keys=keys("access"),release_keys=keys("release"),
                        minimum_sequence=config["minimum_sequence"],preservation_authorities=authorities)
        from .authority import Principal
        principals=[Principal(row["subject"],row["tenant"],frozenset(row["scopes"])) for row in config.get("proposal_principals",[])]
        stop,thread=app.start_proposal_loop(principals,interval_seconds=config.get("proposal_interval_seconds",60))
        http=server(app,port=args.port)
        print(json.dumps({"listening":"http://127.0.0.1:"+str(http.server_port),"mode":"RESEARCH"}),flush=True)
        try:http.serve_forever()
        except KeyboardInterrupt:pass
        finally:
            stop.set();thread.join(timeout=1);http.server_close()
        return
    print(json.dumps(result,sort_keys=True,allow_nan=False))


if __name__=="__main__":main()
