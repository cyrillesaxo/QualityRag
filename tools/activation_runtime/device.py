"""Bounded module planning, resumable object downloads and signed atomic activation."""
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from time import perf_counter_ns

from .artifacts import ArtifactStore
from .common import canonical, fingerprint, HEX


def sparse_plan(modules,required, *, max_memory_bytes,max_compute_units):
    if not isinstance(modules,dict) or not isinstance(required,list) or len(modules)>64:
        raise ValueError("Bounded module catalog required")
    if type(max_memory_bytes) is not int or type(max_compute_units) is not int or min(max_memory_bytes,max_compute_units)<0:
        raise ValueError("Integer resource budgets required")
    selected=set();visiting=set()
    def visit(name):
        if name in visiting: raise ValueError("Dependency cycle")
        if name in selected: return
        if name not in modules: raise ValueError("Missing required module")
        m=modules[name]
        if set(m)!={"dependencies","memory_bytes","compute_units","hash"} or not HEX.fullmatch(m["hash"]):
            raise ValueError("Invalid module contract")
        if any(type(m[k]) is not int or m[k]<0 for k in ("memory_bytes","compute_units")):
            raise ValueError("Invalid module resource bound")
        visiting.add(name)
        for dependency in m["dependencies"]:visit(dependency)
        visiting.remove(name);selected.add(name)
    for name in required:visit(name)
    memory=sum(modules[n]["memory_bytes"] for n in selected)
    compute=sum(modules[n]["compute_units"] for n in selected)
    return {"selected":sorted(selected),"rationale":"Transitive closure of explicitly required capabilities",
            "memory_bound_bytes":memory,"compute_bound_units":compute,
            "action":"ACTIVATE" if memory<=max_memory_bytes and compute<=max_compute_units else "FALLBACK",
            "full_memory_bytes":sum(m["memory_bytes"] for m in modules.values()),
            "energy_measurement":"UNKNOWN"}


class ModuleUpdater:
    """Host filesystem is trusted. Signed compatibility must be verified before activate."""
    def __init__(self,root,*,tenant):
        self.store=ArtifactStore(Path(root)/"objects",tenant=tenant)
        self.state=Path(root)/"updates"/tenant
        self.state.mkdir(parents=True,exist_ok=True)

    def append(self,address,chunk,*,offset,total):
        if not isinstance(address,str) or not HEX.fullmatch(address) or not isinstance(chunk,bytes):
            raise ValueError("Invalid module download")
        if any(type(v) is not int for v in (offset,total)) or not 0<=offset<=total<=2_000_000 or offset+len(chunk)>total:
            raise ValueError("Download budget")
        path=self.state/(address+".partial")
        if path.is_symlink():raise ValueError("Symlink download prohibited")
        actual=path.stat().st_size if path.exists() else 0
        if actual!=offset:raise ValueError("Resume offset mismatch")
        with path.open("ab") as f:
            f.write(chunk);f.flush();os.fsync(f.fileno())
        if path.stat().st_size==total:
            data=path.read_bytes()
            if sha256(data).hexdigest()!=address:
                path.unlink();raise ValueError("Downloaded module integrity mismatch")
            self.store.put(data);path.unlink()
            return {"status":"COMPLETE","downloaded_bytes":total}
        return {"status":"PARTIAL","downloaded_bytes":offset+len(chunk)}

    def activate(self,address,*,signed_manifest,trusted_keys,binding,minimum_sequence,as_of):
        from .artifacts import verify_manifest
        verified_manifest=verify_manifest(signed_manifest,trusted_keys,store=self.store,
            tenant=self.store.tenant,minimum_sequence=minimum_sequence,as_of=as_of,**binding)
        if address not in verified_manifest["resolved_modules"]:
            raise PermissionError("Module not covered by signed scoped manifest")
        self.store.get(address)
        pointer=self.state/"active.json"
        prior=json.loads(pointer.read_text()) if pointer.exists() else None
        body={"address":address,"previous":prior["address"] if prior else None,
              "manifest_sha256":verified_manifest["manifest_sha256"]}
        fd,temp=tempfile.mkstemp(dir=self.state)
        try:
            with os.fdopen(fd,"wb") as f:f.write(canonical(body));f.flush();os.fsync(f.fileno())
            os.replace(temp,pointer)
        finally:
            if os.path.exists(temp):os.unlink(temp)
        return body


def compile_sparse_scene(payload,model):
    """Compile away unused palette modules, remapping all exact residual references."""
    from copy import deepcopy
    from .scene_codec import digest,decode_frames,canon
    original=decode_frames(payload,model)
    active=sorted({row["backdrop"] for row in payload["frames"]})
    remap={old:new for new,old in enumerate(active)}
    sparse_model={**deepcopy(model),"palette":[model["palette"][i] for i in active]}
    sparse_payload=deepcopy(payload)
    for row in sparse_payload["frames"]:row["backdrop"]=remap[row["backdrop"]]
    sparse_payload["model_sha256"]=digest(sparse_model)
    if decode_frames(sparse_payload,sparse_model)!=original:
        raise ValueError("Sparse compilation changed exact frames")
    return sparse_payload,sparse_model,{"selected_modules":active,"rationale":"Only referenced backdrop codes retained",
        "full_model_bytes":len(canon(model)),"sparse_model_bytes":len(canon(sparse_model)),
        "fidelity":"EXACT_NORMALIZED_FRAME_MATCH","signature":"NEW_RELEASE_SIGNATURE_REQUIRED"}
