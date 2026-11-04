"""Source-anchored preservation obligations and typed observation IR.

These are finite data contracts. Reviewed labels never authenticate a domain
reviewer; callers must pass signed bindings through the authority layer.
"""
from hashlib import sha256
import math
from fractions import Fraction

from .common import canonical, fingerprint, identity
from .pipeline import encode
from finite_activation import parse_source


def make_contract(raw, *, task, author, reviewer, tenant, ir, obligations):
    from unified_gate import _checked_ir
    _checked_ir(ir)
    values = parse_source(raw)
    for value in (task,author,reviewer,tenant):
        identity(value)
    if author == reviewer:
        raise ValueError("Independent reviewer identity required")
    if not isinstance(obligations,list) or not 1 <= len(obligations) <= 128:
        raise ValueError("Bounded obligations required")
    nodes={n["node_id"] for n in ir["nodes"]}
    fields=set()
    checked=[]
    for row in obligations:
        if not isinstance(row,dict) or set(row)!={"field","ir_node_id","mode","tolerance","omission_permitted"}:
            raise ValueError("Typed preservation obligation required")
        field=row["field"]
        if not isinstance(field,str) or not isinstance(row["ir_node_id"],str) or field not in values or field in fields or row["ir_node_id"] not in nodes:
            raise ValueError("Missing/duplicate source field or unknown IR node")
        fields.add(field)
        mode=row["mode"]
        tol=row["tolerance"]
        if mode not in {"EXACT","APPROXIMATE","UNKNOWN"} or type(row["omission_permitted"]) is not bool:
            raise ValueError("Invalid preservation mode")
        if mode=="APPROXIMATE":
            if _decimal(tol) < 0 or type(values[field]) not in (float,int):
                raise ValueError("Numeric approximation requires finite tolerance")
        elif tol is not None:
            raise ValueError("Tolerance only valid for approximation")
        if row["omission_permitted"] and mode in {"EXACT","UNKNOWN"}:
            raise ValueError("Exact/unknown distinctions cannot be omitted")
        checked.append({**row,"anchor":{"kind":"json-key","key":field,
                         "value_sha256":fingerprint(values[field])}})
    return {"schema":"qualityrag.preservation-contract/v1","task":task,"tenant":tenant,
            "author":author,"reviewer":reviewer,"version":"1.0",
            "source_sha256":sha256(raw).hexdigest(),"ir_sha256":ir["ir_sha256"],
            "policy_source_sha256":ir["source"]["sha256"],
            "obligations":checked,"unspecified_fields":sorted(set(values)-fields),
            "default_unspecified":"PRESERVE_IN_RESIDUAL",
            "authorization":"REQUIRES_SIGNED_REVIEW"}


def _decimal(value):
    if type(value) is int:return Fraction(value)
    if type(value) is float and math.isfinite(value):return Fraction(str(value))
    raise ValueError("Finite numeric value required")


def _validated_contract(raw,contract,current_ir):
    if not isinstance(contract,dict):raise ValueError("Preservation contract required")
    keys={"schema","task","tenant","author","reviewer","version","source_sha256","ir_sha256",
          "policy_source_sha256","obligations","unspecified_fields","default_unspecified","authorization"}
    if set(contract)!=keys:raise ValueError("Unsupported preservation contract shape")
    rows=contract["obligations"]
    if not isinstance(rows,list) or any(not isinstance(row,dict) or set(row)!={"field","ir_node_id","mode","tolerance","omission_permitted","anchor"} for row in rows):
        raise ValueError("Invalid preservation obligation anchors")
    expected=make_contract(raw,task=contract["task"],author=contract["author"],reviewer=contract["reviewer"],
        tenant=contract["tenant"],ir=current_ir,
        obligations=[{key:value for key,value in row.items() if key!="anchor"} for row in rows])
    if canonical(contract)!=canonical(expected):raise ValueError("Stale or altered preservation contract/source/policy")
    return parse_source(raw)


def _checked_output(output):
    if not isinstance(output,dict) or any(not isinstance(key,str) for key in output):raise ValueError("Flat structured output required")
    if output:parse_source(canonical(output))
    return output


def omission_context(raw,output,contract,*,current_ir):
    """Draft the exact scope to review; this does not grant omission authority."""
    values=_validated_contract(raw,contract,current_ir);_checked_output(output)
    omitted=sorted(set(values)-set(output))
    if not omitted:raise ValueError("No omissions to authorize")
    return {"purpose":"PRESERVATION_OUTPUT_OMISSION","tenant":contract["tenant"],"task":contract["task"],
            "source_sha256":contract["source_sha256"],"policy_ir_sha256":current_ir["ir_sha256"],
            "policy_source_sha256":current_ir["source"]["sha256"],"contract_sha256":fingerprint(contract),
            "output_sha256":fingerprint(output),"omitted_fields":omitted}


def _check_signer(signed_review,reviewer_keys,reviewer_subjects,*,context,contract,author_public_key,as_of):
    from .authority import check_review
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    if not isinstance(author_public_key,Ed25519PublicKey):raise PermissionError("Host author verification key required")
    if not isinstance(reviewer_subjects,dict) or not isinstance(reviewer_keys,dict) or set(reviewer_subjects)!=set(reviewer_keys):
        raise PermissionError("Complete host reviewer subject map required")
    checked=check_review(signed_review,reviewer_keys,context=context,author_public_key=author_public_key,as_of=as_of)
    subject=reviewer_subjects[checked["review_key_id"]];identity(subject)
    if subject!=checked["reviewer"] or subject!=contract["reviewer"]:
        raise PermissionError("Review signer differs from host subject or contract reviewer")


def audit_output(raw, output, contract, *, current_ir, omission_reviewed=False,
                 signed_omission_review=None,reviewer_keys=None,reviewer_subjects=None,
                 author_public_key=None,as_of=None,nonce_store=None):
    if omission_reviewed is not False:raise PermissionError("Boolean omission approval is no longer accepted")
    values=_validated_contract(raw,contract,current_ir);_checked_output(output)
    inventory={name:[] for name in ("preserved","approximated","omitted","unknown","residual_required","violations")}
    by_field={row["field"]:row for row in contract["obligations"]};pending=[]
    for field,expected in values.items():
        row=by_field.get(field)
        if row and row["mode"]=="UNKNOWN":inventory["unknown"].append(field)
        if field not in output:
            if row and row["omission_permitted"]:pending.append(row)
            else:
                inventory["residual_required"].append(field)
                inventory["violations"].append({"field":field,"reason":"UNAUTHORIZED_OMISSION"})
            continue
        actual=output[field]
        if fingerprint(actual)==fingerprint(expected):inventory["preserved"].append(field)
        elif row and row["mode"]=="APPROXIMATE" and type(actual) in (float,int) and abs(_decimal(actual)-_decimal(expected))<=_decimal(row["tolerance"]):
            inventory["approximated"].append(field)
        else:inventory["violations"].append({"field":field,"reason":"CHANGED_REQUIRED_DISTINCTION"})
    for field in sorted(set(output)-set(values)):
        inventory["violations"].append({"field":field,"reason":"INVENTED_FIELD"})
    approval=None
    if signed_omission_review is not None:
        if not pending or inventory["violations"]:raise ValueError("Omission review cannot authorize an otherwise invalid output")
        from .authority import verify_review
        context=omission_context(raw,output,contract,current_ir=current_ir)
        _check_signer(signed_omission_review,reviewer_keys,reviewer_subjects,context=context,contract=contract,
                      author_public_key=author_public_key,as_of=as_of)
        approval=verify_review(signed_omission_review,reviewer_keys,context=context,author_public_key=author_public_key,
            as_of=as_of,nonce_store=nonce_store,tenant=contract["tenant"],reviewer_subjects=reviewer_subjects)
        inventory["omitted"]=[{"field":row["field"],"ir_node_id":row["ir_node_id"]} for row in pending]
    else:
        for row in pending:
            inventory["residual_required"].append(row["field"])
            inventory["violations"].append({"field":row["field"],"reason":"UNAUTHORIZED_OMISSION"})
    return {"schema":"qualityrag.omission-audit/v1",**inventory,"omission_review":approval,
            "finite_constraint_result":"UNSAT" if inventory["violations"] else "SAT",
            "qualityrag_admission":"INCONCLUSIVE","can_generate":False,
            "source_sha256":contract["source_sha256"],"policy_ir_sha256":current_ir["ir_sha256"]}


def observation(raw, *, observation_id, quote_start, quote_end, kind, value, roles,
                polarity, quantity, unit, temporal_order, modality):
    """Typed exact UTF-8 character and byte anchors; no free-form role inference."""
    identity(observation_id)
    text=raw.decode("utf-8")
    if (type(quote_start) is not int or type(quote_end) is not int
            or not 0 <= quote_start < quote_end <= len(text)):
        raise ValueError("Invalid observation source span")
    if kind not in {"ENTITY","RELATION","EVENT","UNKNOWN"} or polarity not in {"POSITIVE","NEGATIVE","UNKNOWN"}:
        raise ValueError("Unsupported semantic type/polarity")
    if not isinstance(roles,dict) or set(roles)-{"actor","recipient","beneficiary","subject","object"}:
        raise ValueError("Invalid typed role")
    for role in roles.values():
        identity(role)
    if quantity is not None and (type(quantity) not in (float,int) or not math.isfinite(quantity) or not isinstance(unit,str) or not unit):
        raise ValueError("Quantity requires finite value and explicit unit")
    if quantity is None and unit is not None:
        raise ValueError("Unit without quantity")
    if modality not in {"OBSERVED","REQUIRED","PERMITTED","PROHIBITED","UNKNOWN"}:
        raise ValueError("Invalid modality")
    if not isinstance(temporal_order,list) or len(temporal_order)>32 or len(set(temporal_order))!=len(temporal_order):
        raise ValueError("Invalid temporal order")
    for item in temporal_order:
        identity(item)
    quote=text[quote_start:quote_end]
    return {"schema":"qualityrag.semantic-observation/v1","id":observation_id,"kind":kind,
            "value":value,"roles":roles,"polarity":polarity,"quantity":quantity,"unit":unit,
            "temporal_order":temporal_order,"modality":modality,
            "source":{"sha256":sha256(raw).hexdigest(),"char_start":quote_start,"char_end":quote_end,
                      "byte_start":len(text[:quote_start].encode()),"byte_end":len(text[:quote_end].encode()),
                      "quote":quote,"quote_sha256":sha256(quote.encode()).hexdigest()},
            "domain_validity":"UNKNOWN"}


def bind_reviewed_contract(raw,contract,ir,*,signed_review,reviewer_keys,reviewer_subjects,author_public_key,as_of,nonce_store):
    """Verify an independent host subject over a reconstructible contract."""
    from .authority import verify_review
    _validated_contract(raw,contract,ir)
    context={"purpose":"PRESERVATION_CONTRACT_REVIEW","source_sha256":contract["source_sha256"],
             "policy_ir_sha256":ir["ir_sha256"],"policy_source_sha256":ir["source"]["sha256"],
             "contract_sha256":fingerprint(contract)}
    _check_signer(signed_review,reviewer_keys,reviewer_subjects,context=context,contract=contract,
                  author_public_key=author_public_key,as_of=as_of)
    reviewed=verify_review(signed_review,reviewer_keys,context=context,author_public_key=author_public_key,
        as_of=as_of,nonce_store=nonce_store,tenant=contract["tenant"],reviewer_subjects=reviewer_subjects)
    return {"schema":"qualityrag.reviewed-preservation-binding/v1","context":context,"review":reviewed,
            "domain_admission":"INCONCLUSIVE","can_generate":False}
