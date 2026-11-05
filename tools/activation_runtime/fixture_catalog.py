"""Emit valid authored examples for each schema, with actual compiled policy/receipt."""
import json
from pathlib import Path
import tempfile
from .demo import run
from .pipeline import encode


def generate(output):
    root=Path(output);root.mkdir(parents=True,exist_ok=True)
    source={"actor":"supplier","recipient":"buyer","polarity":"NOT"}
    from .common import canonical
    artifact=encode(canonical(source),{"actor":"a","recipient":"b","polarity":"p"})
    with tempfile.TemporaryDirectory() as temp:
        out=Path(temp)/"demo";data=run(out)
        policy=json.loads((out/"policy-ir.json").read_bytes())
        receipt=data["cases"][0]["receipt"]
    examples={"source":source,"payload":artifact["payload"],"transform":artifact,"packspec":policy,
        "grammar":{"schema":"rct.typed-operator-grammar/v1.4","predicate_types":{"p":["actor","recipient"]},
                   "operators":["EDGE"],"max_ast_nodes":1,"max_candidates":10},
        "operator-ast":{"op":"EDGE","predicate":"p"},
        "verdict":{"finite_constraint_result":"SAT","qualityrag_admission":"INCONCLUSIVE","can_generate":False},
        "receipt":receipt}
    from .contracts import validate
    for name,value in examples.items():
        validate(name,value)
        if name=="source":(root/(name+".json")).write_bytes(canonical(value))
        else:(root/(name+".json")).write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
    return examples


if __name__=="__main__":
    generate(Path(__file__).with_name("fixtures"))
