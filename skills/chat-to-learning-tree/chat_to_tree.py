#!/usr/bin/env python3
"""Deterministic candidate extractor. NOT semantic FF-RCT induction or evidence verification."""
import argparse, hashlib, json, re
from pathlib import Path

CONCEPTS = {
  "transformer": "Transformer architecture", "attention": "Self-attention",
  "neuron": "Neurons and layers", "packspec": "PackSpec", "qualityrag": "QualityRAG",
  "fractal": "Fractal expansion", "ladder": "Learning Ladder",
  "kafka": "Kafka", "kubernetes": "Kubernetes", "rag": "Retrieval-augmented generation",
  "vector database": "Vector databases", "spring boot": "Spring Boot",
  "neural network": "Neural networks", "token": "Tokens", "autofill": "Autofill",
}

def messages(source):
    if isinstance(source, str):
        if not source.strip() or len(source)>100000: raise ValueError("Invalid text length")
        return [{"role":"unknown","text":x.strip()} for x in re.split(r"(?im)^\\s*(?:User|Assistant|Human|AI):\\s*",source) if x.strip()]
    if isinstance(source,dict): source=source.get("messages")
    if not isinstance(source,list) or not source: raise ValueError("Expected messages array or text")
    items=[]
    for m in source:
        if not isinstance(m,dict): raise ValueError("Invalid message")
        content=m.get("content",m.get("text",""))
        if not isinstance(content,str): raise ValueError("Text-only messages required")
        items.append({"role":str(m.get("role","unknown")),"text":content})
    if sum(len(m["text"]) for m in items)>100000: raise ValueError("Too large")
    return items

def convert(source,title="Imported conversation",max_children=5):
    if not 1<=max_children<=12: raise ValueError("max_children out of range")
    items=messages(source)
    canonical=json.dumps(items,sort_keys=True,ensure_ascii=False,separators=(",",":"))
    digest=hashlib.sha256(canonical.encode()).hexdigest()
    hits={}
    for idx,m in enumerate(items):
        for key,label in CONCEPTS.items():
            if re.search(r"(?<!\\w)"+re.escape(key)+r"s?(?!\\w)",m["text"],re.I):
                hits.setdefault(label,[]).append(idx)
    selected=sorted(hits.items(),key=lambda x:(-len(x[1]),x[0]))[:max_children]
    nodes=[{"id":"root","label":title[:140],"parent":None,"status":"candidate","source_message_ids":list(range(len(items)))}]
    for i,(label,refs) in enumerate(selected,1):
        nodes.append({"id":f"concept-{i}","label":label,"parent":"root","status":"candidate",
          "source_message_ids":refs,"pack_spec":{"objective":f"Understand {label}",
          "required_claims":[],"exceptions":[],"verification":"INCONCLUSIVE"}})
    return {"schema":"ff-rct-learning-tree/candidate-v0.1",
      "source":{"sha256":digest,"message_count":len(items),"original_immutable":True},
      "root_pack_spec":{"objective":f"Understand {title[:140]}","essential_claims":[],
        "exceptions":[],"source_coverage":"unreviewed","verification":"INCONCLUSIVE"},
      "nodes":nodes,"edges":[{"from":"root","to":n["id"],"type":"EXPAND_CANDIDATE"} for n in nodes[1:]],
      "unresolved":["Keyword matching is not semantic understanding",
        "Independent evidence checks not executed","Dependencies and exceptions unverified"],
      "shorts":[]}
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("input",type=Path);p.add_argument("-o","--output",required=True,type=Path)
    p.add_argument("--title",default="Imported conversation");p.add_argument("--max-children",type=int,default=5)
    a=p.parse_args()
    text=a.input.read_text(encoding="utf-8")
    input_data=json.loads(text) if a.input.suffix.lower()==".json" else text
    a.output.write_text(json.dumps(convert(input_data,a.title,a.max_children),indent=2,ensure_ascii=False)+"\\n",encoding="utf-8")
