"""Bounded, tenant-scoped PostgreSQL graph context retrieval."""
from __future__ import annotations
from collections import deque

def query_context_postgres(store, *, principal, authorize, object_id, revision,
                           max_hops=1, max_nodes=30, max_edges=200,
                           layers=("KNOWLEDGE","WITNESS")):
    if not isinstance(principal,str) or not principal.strip() or not callable(authorize):
        raise PermissionError("Principal and object authorizer are required")
    if (type(max_hops) is not int or max_hops not in range(6)
            or type(max_nodes) is not int or not 1<=max_nodes<=100
            or type(max_edges) is not int or not 1<=max_edges<=1000):
        raise ValueError("Query limits exceeded")
    if not isinstance(layers,tuple) or not layers or any(
            x not in ("KNOWLEDGE","WITNESS","REGIME") for x in layers):
        raise ValueError("Invalid layer set")
    if not authorize(principal,object_id,revision):
        raise PermissionError("Root object denied")
    if store.object_version(object_id,revision) is None:
        return {"schema":"qualityrag.semantic-context/v0.1",
                "status":"NOT_FOUND","nodes":[],"edges":[],
                "admission":"INCONCLUSIVE"}
    seen=set(); queue=deque([(object_id,revision,0)])
    nodes=[]; edges=[]; truncated=False
    while queue and len(nodes)<max_nodes:
        oid,rev,depth=queue.popleft()
        if (oid,rev) in seen or not authorize(principal,oid,rev):
            continue
        payload=store.object_version(oid,rev)
        if payload is None:
            continue
        seen.add((oid,rev))
        nodes.append({"object_id":oid,"revision":rev,"payload":payload})
        if depth>=max_hops:
            continue
        available=max_edges-len(edges)
        if available<=0:
            truncated=True
            break
        candidates=store.read_edges(oid,rev,limit=available+1)
        if len(candidates)>available:
            truncated=True
        for e in candidates[:available]:
            dest=e["to_id"],e["to_revision"]
            if e["layer"] not in layers or not authorize(principal,*dest):
                continue
            if store.object_version(*dest) is None:
                continue
            edges.append(e)
            if dest not in seen:
                queue.append((*dest,depth+1))
    if queue:
        truncated=True
    visible={(n["object_id"],n["revision"]) for n in nodes}
    edges=[e for e in edges if (e["from_id"],e["from_revision"]) in visible
           and (e["to_id"],e["to_revision"]) in visible]
    return {"schema":"qualityrag.semantic-context/v0.1",
            "status":"BOUNDED_CONTEXT","nodes":nodes,"edges":edges,
            "admission":"INCONCLUSIVE","verification":"NOT_PERFORMED",
            "limits":{"max_hops":max_hops,"max_nodes":max_nodes,
                      "max_edges":max_edges,"truncated":truncated}}
