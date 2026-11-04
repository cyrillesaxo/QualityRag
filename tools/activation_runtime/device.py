"""Bounded module planning, resumable object downloads and signed atomic activation."""
from hashlib import sha256
import json
import stat
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
from time import perf_counter_ns

from .artifacts import ArtifactStore
from .common import canonical, fingerprint, HEX, strict_json


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
        if self.state.is_symlink():raise ValueError("Symlink update state prohibited")

    @contextmanager
    def _locked(self):
        # POSIX filesystem reference. Never wait indefinitely on a competing writer.
        import fcntl
        fd=os.open(self.state/"update.lock",os.O_CREAT|os.O_RDWR|getattr(os,"O_NOFOLLOW",0),0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError("Regular update lock required")
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:raise ValueError("Update busy; retry without changing offset") from exc
            yield
        finally:os.close(fd)

    def _sync(self,directory=None):
        fd=os.open(self.state if directory is None else directory,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
        try:os.fsync(fd)
        finally:os.close(fd)

    def _write(self,path,body):
        fd,temp=tempfile.mkstemp(dir=self.state)
        try:
            with os.fdopen(fd,"wb") as f:f.write(canonical(body));f.flush();os.fsync(f.fileno())
            os.replace(temp,path);self._sync()
        finally:
            if os.path.exists(temp):os.unlink(temp)

    def _read(self,path):
        fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
        with os.fdopen(fd,"rb") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError("Regular update state required")
            return strict_json(f.read(524289))

    def progress(self,address):
        """Report durable local transfer bytes; never infer network or energy costs."""
        self.store._path(address)
        with self._locked():
            try:cached=self.store.get(address)
            except FileNotFoundError:cached=None
            if cached is not None:
                return {"status":"COMPLETE","downloaded_bytes":len(cached),"total":len(cached),
                        "cached_object_bytes":len(cached)}
            path=self.state/(address+".partial");meta=self.state/(address+".download.json")
            if path.is_symlink() or meta.is_symlink():raise ValueError("Symlink download prohibited")
            if not meta.exists():
                if path.exists():raise ValueError("Unbound legacy partial; explicitly discard before retry")
                return {"status":"NOT_STARTED","downloaded_bytes":0,"total":None,"cached_object_bytes":0}
            row=self._read(meta)
            if (not isinstance(row,dict) or set(row)!={"schema","address","total"} or
                row["schema"]!="qualityrag.module-download/v1" or row["address"]!=address or
                type(row["total"]) is not int or not 1<=row["total"]<=2_000_000):
                raise ValueError("Invalid persisted transfer metadata")
            size=path.stat().st_size if path.exists() else 0
            if not 0<=size<=row["total"]:raise ValueError("Invalid persisted transfer length")
            return {"status":"PARTIAL","downloaded_bytes":size,"total":row["total"],"cached_object_bytes":0}

    def discard_partial(self,address):
        """Explicitly abandon an interrupted transfer, preserving verified cached objects."""
        self.store._path(address)
        with self._locked():
            for suffix in (".partial",".download.json"):
                (self.state/(address+suffix)).unlink(missing_ok=True)
            self._sync()

    def append(self,address,chunk,*,offset,total):
        if not isinstance(address,str) or not HEX.fullmatch(address) or not isinstance(chunk,bytes):
            raise ValueError("Invalid module download")
        if any(type(v) is not int for v in (offset,total)) or not 0<=offset<=total<=2_000_000 or total==0 or offset+len(chunk)>total:
            raise ValueError("Download budget")
        with self._locked():
            path=self.state/(address+".partial");meta=self.state/(address+".download.json")
            if path.is_symlink() or meta.is_symlink():raise ValueError("Symlink download prohibited")
            # Publication can succeed before cleanup or the caller receives a reply.
            # An exact retransmission must reuse the immutable, hash-verified object.
            try:cached=self.store.get(address)
            except FileNotFoundError:cached=None
            if cached is not None:
                if len(cached)!=total or cached[offset:offset+len(chunk)]!=chunk:
                    raise ValueError("Cached object disagrees with transfer")
                self._sync(self.store.root)
                path.unlink(missing_ok=True);meta.unlink(missing_ok=True);self._sync()
                return {"status":"COMPLETE","downloaded_bytes":total,"received_bytes":len(chunk),
                        "written_bytes":0,"cached_object_bytes":total,"cache_hit":True}
            expected={"schema":"qualityrag.module-download/v1","address":address,"total":total}
            if meta.exists():
                if self._read(meta)!=expected:raise ValueError("Resume total or address mismatch")
            else:
                if path.exists() and path.stat().st_size:raise ValueError("Unbound legacy partial; explicitly discard before retry")
                if offset!=0:raise ValueError("Resume offset mismatch")
                self._write(meta,expected)
            fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_APPEND|getattr(os,"O_NOFOLLOW",0),0o600)
            with os.fdopen(fd,"ab") as f:
                info=os.fstat(f.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size!=offset:raise ValueError("Resume offset mismatch")
                f.write(chunk);f.flush();os.fsync(f.fileno())
            self._sync()
            size=path.stat().st_size
            if size==total:
                data=path.read_bytes()
                if sha256(data).hexdigest()!=address:
                    path.unlink();meta.unlink();self._sync()
                    raise ValueError("Downloaded module integrity mismatch")
                self.store.put(data)
                # The object directory entry must be durable before dropping recovery data.
                self._sync(self.store.root)
                path.unlink();meta.unlink();self._sync()
                return {"status":"COMPLETE","downloaded_bytes":total,"received_bytes":len(chunk),
                        "written_bytes":len(chunk),"cached_object_bytes":total,"cache_hit":False}
            return {"status":"PARTIAL","downloaded_bytes":size,"received_bytes":len(chunk),
                    "written_bytes":len(chunk),"cached_object_bytes":0,"cache_hit":False}

    def activate(self,address,*,signed_manifest,trusted_keys,binding,minimum_sequence,as_of):
        from .artifacts import verify_manifest
        with self._locked():
            verified_manifest=verify_manifest(signed_manifest,trusted_keys,store=self.store,
                tenant=self.store.tenant,minimum_sequence=minimum_sequence,as_of=as_of,**binding)
            if address not in verified_manifest["resolved_modules"]:
                raise PermissionError("Module not covered by signed scoped manifest")
            raw=self.store.get(address)
            pointer=self.state/"active.json"
            prior=self._read(pointer) if pointer.exists() else None
            body={"address":address,"previous":prior["address"] if prior else None,
                  "manifest_sha256":verified_manifest["manifest_sha256"],
                  "sequence":verified_manifest["manifest"]["sequence"],"cached_object_bytes":len(raw)}
            self._write(pointer,body)
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
