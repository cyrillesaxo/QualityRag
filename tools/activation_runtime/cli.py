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


def contract_keygen(out,key_id):
    """Private key stays with the contract governor (mode 0600); only public keys are distributed:
    DER/SPKI base64url for the registry trust store, raw base64 for the runtime."""
    import base64,os
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,PublicFormat,NoEncryption
    from .common import identity
    identity(key_id)
    folder=Path(out);folder.mkdir(parents=True,exist_ok=True)
    key=Ed25519PrivateKey.generate();private=folder/(key_id+".key")
    fd=os.open(private,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as f:f.write(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()))
    pub=key.public_key()
    der=base64.urlsafe_b64encode(pub.public_bytes(Encoding.DER,PublicFormat.SubjectPublicKeyInfo)).decode().rstrip("=")
    raw=base64.b64encode(pub.public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
    (folder/(key_id+".registry-trust.json")).write_text(json.dumps({key_id:der}))
    return {"private_key":str(private),"registry_trust_store":{key_id:der},"runtime_public_key":{key_id:raw}}


def main(argv=None):
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("catalog")
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
    p=sub.add_parser("garden",help="query and grow the Semantic Gardener research tree")
    p.add_argument("action",choices=["state","query","suggestions","event","watch","evolution"])
    p.add_argument("--endpoint",required=True);p.add_argument("--token",required=True)
    p.add_argument("--text");p.add_argument("--evidence-status");p.add_argument("--lineage-of");p.add_argument("--depends-on")
    p.add_argument("--open-challenge",action="store_true");p.add_argument("--active-only",action="store_true")
    p.add_argument("--since",type=int,default=0);p.add_argument("--limit",type=int,default=200)
    p.add_argument("--request",help="event JSON for the event action")
    p.add_argument("--interval",type=float,default=2.0);p.add_argument("--max-polls",type=int,default=0,help="watch: stop after N polls (0 = until interrupted)")
    p=sub.add_parser("contract-keygen",help="create a contract-governor Ed25519 key pair (ADR-0002)")
    p.add_argument("--out",required=True);p.add_argument("--key-id",required=True)
    p=sub.add_parser("contract-sign",help="sign a data contract offline for registry staging (ADR-0002)")
    p.add_argument("--contract",required=True);p.add_argument("--key",required=True);p.add_argument("--key-id",required=True)
    p.add_argument("--sequence",type=int,required=True);p.add_argument("--hours",type=int,default=24*7)
    p=sub.add_parser("serve");p.add_argument("--root",required=True);p.add_argument("--keys",required=True);p.add_argument("--port",type=int,default=8769)
    args=parser.parse_args(argv)
    if args.command=="catalog":
        from .contracts import catalog_report
        result=catalog_report()
    elif args.command=="validate":
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
    elif args.command=="garden":
        sdk=str(Path(__file__).resolve().parents[2]/"sdk"/"python")
        if sdk not in sys.path:sys.path.insert(0,sdk)
        from qualityrag_activation import Client
        client=Client(args.endpoint,read(args.token))
        filters={k:v for k,v in {"text":args.text,"evidence_status":args.evidence_status,"lineage_of":args.lineage_of,"depends_on":args.depends_on,
                 "open_challenge":True if args.open_challenge else None,"active":True if args.active_only else None,
                 "limit":args.limit}.items() if v is not None}
        if args.action=="state":result=client.garden_state()
        elif args.action=="evolution":result=client.garden_evolution()
        elif args.action=="suggestions":result=client.garden_suggestions()
        elif args.action=="event":
            if not args.request:raise ValueError("--request event JSON required")
            result=client.garden_event(**read(args.request))
        elif args.action=="query":result=client.garden_query(since=args.since,**filters)
        else:
            # Stream the tree's growth as JSON lines: one line per new event.
            if not 0.5<=args.interval<=300:raise ValueError("Watch interval between 0.5 and 300 seconds")
            import time
            since,polls=args.since,0
            while True:
                delta=client.garden_query(since=since,limit=1)
                for event in delta["events"]:print(json.dumps(event,sort_keys=True),flush=True)
                since=delta["head_sequence"] if not delta["events_truncated"] else since+len(delta["events"])
                polls+=1
                if args.max_polls and polls>=args.max_polls:return
                time.sleep(args.interval)
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
    elif args.command=="contract-keygen":result=contract_keygen(args.out,args.key_id)
    elif args.command=="contract-sign":
        from datetime import datetime,timedelta,timezone
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from .protection import sign_contract
        if not 1<=args.hours<=24*30:raise ValueError("Validity must be 1 hour to 30 days")
        raw=Path(args.key).read_bytes()
        if len(raw)!=32:raise ValueError("Expected a 32-byte raw Ed25519 private key")
        now=datetime.now(timezone.utc).replace(microsecond=0)
        stamp=lambda v:v.isoformat().replace("+00:00","Z")
        result=sign_contract(read(args.contract),Ed25519PrivateKey.from_private_bytes(raw),key_id=args.key_id,
                             issued_at=stamp(now),expires_at=stamp(now+timedelta(hours=args.hours)),sequence=args.sequence)
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
                        minimum_sequence=config["minimum_sequence"],preservation_authorities=authorities,
                        protection=config.get("protection"))
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
