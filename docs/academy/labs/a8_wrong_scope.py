"""A8 · Right rule, wrong customer or region. (available pattern + research preview)"""
from _common import AS_OF, ev, evaluate, show
import _research  # noqa: F401
from rct_purpose_lens import make_contract

# Available now: applicability is its own requirement, so a rule for the wrong region can't satisfy it.
pack = {"id": "refund-eligibility-eu", "version": "1.0", "requirements": [
    {"id": "refund-rule", "min_independent_sources": 1},
    {"id": "applies-to-eu", "min_independent_sources": 1}]}
us_policy = ev("refunds-us.html#30-days", "refund-rule", "us-policy-site")  # right rule, US scope only
show("Refund rule found, but it is the US policy", evaluate(pack, [us_policy], as_of=AS_OF))
eu_terms = [ev("refunds-eu.html#14-days", "refund-rule", "eu-policy-site"),
            ev("refunds-eu.html#scope", "applies-to-eu", "eu-policy-site")]
show("EU terms with an explicit scope clause", evaluate(pack, eu_terms, as_of=AS_OF))

# Research preview: a purpose-scoped lens declares which distinctions a purpose must keep.
source = {"schema": "rct.structured-ast/v1", "facts": [
    {"id": "f0", "subject": "policy-eu", "predicate": "applies_to", "object": "eu-consumers", "source_ref": "refunds-eu.html#scope"},
    {"id": "f1", "subject": "policy-eu", "predicate": "grants", "object": "refund-14-days", "source_ref": "refunds-eu.html#14-days"},
    {"id": "f2", "subject": "policy-eu", "predicate": "styled_as", "object": "blue-banner", "source_ref": "refunds-eu.html#banner"}]}
labels = [{"subject": "policy-eu", "object": "refund-14-days", "positive": True, "source_ref": "label#1"}]
c = make_contract(source, labels, purpose="refund-eligibility", required_predicates=["applies_to", "grants"], allowed_omission_predicates=["styled_as"])
print("\n== Purpose contract (research)")
print(f"  purpose: {c['purpose']}   must keep: {', '.join(c['required_predicates'])}   may omit: {', '.join(c['allowed_omission_predicates'])}")
print(f"  review: {c['review']}   admission: {c['qualityrag_admission']}")
try:
    make_contract(source, labels, purpose="refund-eligibility", required_predicates=["grants"], allowed_omission_predicates=["grants"])
except ValueError as e:
    print(f"  a contract that both keeps and omits 'grants' is rejected: {e}")
