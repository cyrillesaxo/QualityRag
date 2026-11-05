"""Composable reversible research grammar; data never becomes executable code."""
import bz2
import json
import struct
import zlib
from hashlib import sha256
from time import perf_counter_ns

MAX_SOURCE=262144
MAX_PACKET=2_000_000


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()


def validate(program):
    if len(canonical(program))>16384:raise ValueError("Compiled grammar byte budget")
    if not isinstance(program,dict) or set(program)!={"schema","rules","activation"} or program["schema"]!="qualityrag.reversible-grammar/v1":
        raise ValueError("Versioned grammar required")
    rules=program["rules"]
    if not isinstance(rules,list) or not 1<=len(rules)<=8:raise ValueError("Grammar node budget")
    for r in rules:
        if not isinstance(r,dict):raise ValueError("Typed rule required")
        op=r.get("op")
        if op in {"zlib","bz2"}:
            if set(r)!={"op","level"} or type(r["level"]) is not int or not 1<=r["level"]<=9:raise ValueError("Compression rule")
        elif op=="delta":
            if set(r)!={"op","stride"} or type(r["stride"]) is not int or not 1<=r["stride"]<=4096:raise ValueError("Delta rule")
        elif op=="xor":
            if set(r)!={"op","value"} or type(r["value"]) is not int or not 0<=r["value"]<=255:raise ValueError("XOR rule")
        elif op=="reverse":
            if set(r)!={"op"}:raise ValueError("Reverse rule")
        elif op=="productions":
            if set(r)!={"op","rules"} or not isinstance(r["rules"],list) or not 1<=len(r["rules"])<=32:raise ValueError("Production budget")
            names=set();literals=set()
            for production in r["rules"]:
                if (not isinstance(production,dict) or set(production)!={"name","literal"}
                        or not isinstance(production["name"],str) or not production["name"].isidentifier()
                        or not 1<=len(production["name"])<=64 or production["name"] in names
                        or not isinstance(production["literal"],str) or not 1<=len(production["literal"].encode())<=256
                        or production["literal"] in literals):raise ValueError("Named literal production required")
                names.add(production["name"]);literals.add(production["literal"])
        else:raise ValueError("Unsupported rule; requires reviewed interpreter extension")
    a=program["activation"]
    if (not isinstance(a,dict) or set(a)!={"mode","chunk_bytes"} or a["mode"] not in {"ON_DEMAND","EAGER"}
            or type(a["chunk_bytes"]) is not int or not 256<=a["chunk_bytes"]<=MAX_SOURCE):
        raise ValueError("Bounded activation plan required")
    return program


def _apply(raw,rule,inverse=False,materialized=None):
    op=rule["op"]
    if op=="productions":
        out=bytearray();i=0
        if inverse:
            cache={}
            while i<len(raw):
                value=raw[i];i+=1
                if value!=255:out.append(value)
                else:
                    if i>=len(raw):raise ValueError("Incomplete production escape")
                    code=raw[i];i+=1
                    if code==255:out.append(255)
                    else:
                        if code>=len(rule["rules"]):raise ValueError("Unknown production")
                        if code not in cache:
                            p=rule["rules"][code];cache[code]=p["literal"].encode()
                            if materialized is not None:materialized.add(p["name"])
                        out.extend(cache[code])
                if len(out)>MAX_PACKET:raise ValueError("Production expansion budget")
        else:
            choices=sorted(enumerate(rule["rules"]),key=lambda p:(-len(p[1]["literal"].encode()),p[0]))
            while i<len(raw):
                match=next(((code,p["literal"].encode()) for code,p in choices if raw.startswith(p["literal"].encode(),i)),None)
                if match:
                    code,literal=match;out.extend((255,code));i+=len(literal)
                else:
                    value=raw[i];i+=1;out.extend((255,255) if value==255 else (value,))
        return bytes(out)
    if op=="zlib":
        if not inverse:return zlib.compress(raw,rule["level"])
        d=zlib.decompressobj();out=d.decompress(raw,MAX_PACKET+1)
        if len(out)>MAX_PACKET or not d.eof or d.unused_data or d.unconsumed_tail:raise ValueError("Residual budget or trailing data")
        return out
    if op=="bz2":
        if not inverse:return bz2.compress(raw,compresslevel=rule["level"])
        d=bz2.BZ2Decompressor();out=d.decompress(raw,max_length=MAX_PACKET+1)
        if len(out)>MAX_PACKET or not d.eof or d.unused_data:raise ValueError("Residual budget or trailing data")
        return out
    if op=="reverse":return raw[::-1]
    if op=="xor":return bytes(v^rule["value"] for v in raw)
    stride=rule["stride"]
    if not inverse:return bytes((v-(raw[i-stride] if i>=stride else 0))%256 for i,v in enumerate(raw))
    out=bytearray()
    for i,v in enumerate(raw):out.append((v+(out[i-stride] if i>=stride else 0))%256)
    return bytes(out)


def encode(raw,program):
    validate(program)
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_SOURCE:raise ValueError("Source budget")
    start=perf_counter_ns();a=program["activation"];chunks=[]
    for offset in range(0,len(raw),a["chunk_bytes"]):
        chunk=raw[offset:offset+a["chunk_bytes"]]
        for rule in program["rules"]:
            chunk=_apply(chunk,rule)
            if len(chunk)>MAX_PACKET:raise ValueError("Intermediate grammar budget")
        chunks.append(chunk)
    header=canonical({"program":program,"length":len(raw),"source_sha256":sha256(raw).hexdigest(),
                      "chunk_sha256":[sha256(raw[i:i+a["chunk_bytes"]]).hexdigest() for i in range(0,len(raw),a["chunk_bytes"])],
                      "chunk_sizes":[len(c) for c in chunks]})
    packet=b"QRG1"+struct.pack(">I",len(header))+header+b"".join(chunks)
    if len(packet)>MAX_PACKET:raise ValueError("Packet budget")
    return packet,{"encode_ns":perf_counter_ns()-start,"program_bytes":len(canonical(program)),
                   "delivered_candidate_bytes":len(packet),"chunks":len(chunks)}


def decode(packet,*,indices=None):
    start=perf_counter_ns()
    if not isinstance(packet,bytes) or not 8<len(packet)<=MAX_PACKET or packet[:4]!=b"QRG1":raise ValueError("Packet header")
    size=struct.unpack(">I",packet[4:8])[0]
    if not 0<size<=262144:raise ValueError("Header budget")
    header=json.loads(packet[8:8+size]);program=validate(header["program"])
    length=header["length"];sizes=header["chunk_sizes"];chunk_bytes=program["activation"]["chunk_bytes"]
    if (type(length) is not int or not 0<length<=MAX_SOURCE or not isinstance(sizes,list)
            or len(sizes)!=(length+chunk_bytes-1)//chunk_bytes or any(type(n) is not int or not 0<n<=MAX_PACKET for n in sizes)
            or sum(sizes)!=len(packet)-8-size):raise ValueError("Chunk inventory")
    requested=list(range(len(sizes))) if indices is None else indices
    if not isinstance(requested,list) or len(set(requested))!=len(requested) or any(type(n) is not int or not 0<=n<len(sizes) for n in requested):raise ValueError("Activation range")
    active=list(range(len(sizes))) if program["activation"]["mode"]=="EAGER" else requested
    offsets=[];offset=8+size
    for n in sizes:offsets.append(offset);offset+=n
    if not isinstance(header.get("chunk_sha256"),list) or len(header["chunk_sha256"])!=len(sizes):raise ValueError("Chunk fidelity inventory")
    output={};trace=[];materialized=set()
    for i in active:
        chunk=packet[offsets[i]:offsets[i]+sizes[i]]
        for rule in reversed(program["rules"]):
            chunk=_apply(chunk,rule,inverse=True,materialized=materialized)
            if len(chunk)>MAX_PACKET:raise ValueError("Reconstruction budget")
            trace.append({"chunk":i,"module":rule["op"]})
        if len(chunk)!=min(chunk_bytes,length-i*chunk_bytes):raise ValueError("Reconstruction length")
        if sha256(chunk).hexdigest()!=header["chunk_sha256"][i]:raise ValueError("Activated chunk fidelity failed")
        output[i]=chunk
    result=b"".join(output[i] for i in requested)
    if requested==list(range(len(sizes))) and sha256(result).hexdigest()!=header["source_sha256"]:raise ValueError("Source fidelity failure")
    return result,{"activation_ns":perf_counter_ns()-start,"activated_chunks":active,
                   "activation_trace":trace,"modules":sorted({r["module"] for r in trace}),
                   "productions_materialized":sorted(materialized)}
