"""Controlled model execution for capability-frontier evaluation.

EXPERIMENTAL: this runner is NOT a secure sandbox or trusted attestation service.
The hosted model API reports token usage; a local auditor verifies answers.
Nothing here grants PackSpec/RCT admission or automatic operator promotion.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
import time
from urllib import request
from urllib.error import HTTPError

from frontier import POLICIES, METRICS, digest, evaluate

RUNNER_SCHEMA = "qualityrag.capability-runner/v0.1"
DEFAULT_POLICIES = {
    "baseline": "Solve the user's problem. Return only the requested answer.",
    "tools": "Solve the user's problem. You may reason using the explicitly provided context. Return only the requested answer.",
    "grammar": "Identify function, boundaries, prerequisites, and invariants. Consider representation changes. Return only the requested answer.",
    "garden": "Identify function and constraints. Consider the supplied unverified operator hypotheses; reject them if their preconditions fail. Return only the requested answer.",
}
# No external tools are configured by this first adapter; the tools condition
# is an ablation label, NOT evidence of a tool-using agent.


def _valid_text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 20000


def _operator_card(operator):
    """Only dev-reviewed cards are eligible; no run-time generated operators."""
    if not isinstance(operator, dict) or any(
        not _valid_text(operator.get(k))
        for k in ("id", "rule", "preconditions", "preserves", "source_ref")
    ):
        raise ValueError("Invalid operator card")
    if operator.get("status") != "REVIEWED_FOR_EXPERIMENT":
        raise ValueError("Operator not approved for experimental use")
    if len(operator["rule"]) > 2000 or len(operator["preconditions"]) > 2000:
        raise ValueError("Operator too long")
    return {k: operator[k] for k in ("id", "rule", "preconditions", "preserves", "source_ref")}


def run_manifest(manifest, adapter, *, audit, trials=3):
    """Execute all four policy conditions and emit paired, auditable run rows.

    The adapter sees ONLY the task prompt and policy guidance, never expected
    answers, gold verification metadata, or holdout labels. This does not
    protect against provider training contamination.
    """
    if not isinstance(manifest, dict) or manifest.get("schema") != RUNNER_SCHEMA:
        raise ValueError("Invalid manifest schema")
    if not callable(adapter) or not callable(audit):
        raise ValueError("Need adapter and independent audit callable")
    cases = manifest.get("cases")
    budget = manifest.get("budget")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Missing cases")
    if not isinstance(budget, dict) or any(type(budget.get(k)) is not int or budget[k] <= 0 for k in METRICS):
        raise ValueError("All budgets must be positive integers")
    if type(trials) is not int or not 2 <= trials <= 20:
        raise ValueError("Invalid trial count")
    operator_cards = [_operator_card(x) for x in manifest.get("operator_cards", [])]
    policy_prompts = manifest.get("policy_prompts", DEFAULT_POLICIES)
    if set(policy_prompts) != set(POLICIES) or any(not _valid_text(x) for x in policy_prompts.values()):
        raise ValueError("Invalid policy prompts")
    if len(cases) > 500 or len(operator_cards) > 50:
        raise ValueError("Experiment too large")
    frozen = deepcopy(cases)
    for case in frozen:
        if not isinstance(case, dict) or not _valid_text(case.get("prompt")):
            raise ValueError("Each case needs a prompt")
        if case.get("split") not in ("development", "holdout") or "expected" not in case:
            raise ValueError("Case must contain split and private expected answer")
    rows = []
    model_id, tools_fingerprint = None, None
    for case in frozen:
        for trial in range(1, trials + 1):
            for policy in POLICIES:
                system = policy_prompts[policy]
                if policy == "garden" and operator_cards:
                    # Only explicitly selected approved, fixed cards. No
                    # mutation or feedback loop can change them during evaluation.
                    system += "\nCANDIDATE OPERATORS (check all preconditions):\n" + json.dumps(
                        operator_cards, sort_keys=True)
                payload = {
                    "system": system, "prompt": case["prompt"],
                    "max_output_tokens": budget["tokens_out"],
                    "policy": policy, "trial": trial, "case_id": case["id"],
                }
                start = time.perf_counter_ns()
                response = adapter(deepcopy(payload))
                measured_ms = max(1, (time.perf_counter_ns() - start) // 1_000_000)
                if not isinstance(response, dict) or not isinstance(response.get("output"), (str, int, float)):
                    raise ValueError("Invalid model response")
                if not _valid_text(response.get("model_id")) or not _valid_text(response.get("tools_fingerprint")):
                    raise ValueError("Adapter lacks model/tool identity")
                if model_id is None:
                    model_id, tools_fingerprint = response["model_id"], response["tools_fingerprint"]
                if (response["model_id"], response["tools_fingerprint"]) != (model_id, tools_fingerprint):
                    raise ValueError("Model or tools changed during a paired experiment")
                if not isinstance(response.get("tokens_in"), int) or not isinstance(response.get("tokens_out"), int):
                    raise ValueError("Adapter did not return token usage")
                if not isinstance(response.get("cost_microusd"), int):
                    raise ValueError("Adapter did not return measured/priced cost")
                output = response["output"]
                verdict = audit(deepcopy(case), output)
                if (not isinstance(verdict, dict) or type(verdict.get("constraint_violations")) is not int
                        or verdict["constraint_violations"] < 0
                        or not _valid_text(verdict.get("auditor_ref"))):
                    raise ValueError("Invalid audit receipt")
                row = {
                    "case_id": case["id"], "trial": trial, "policy": policy,
                    "model_id": model_id, "tools_fingerprint": tools_fingerprint,
                    "output": output, "constraint_violations": verdict["constraint_violations"],
                    "auditor_ref": verdict["auditor_ref"],
                    "tokens_in": response["tokens_in"], "tokens_out": response["tokens_out"],
                    "tool_calls": 0, "wall_ms": measured_ms,
                    "cost_microusd": response["cost_microusd"],
                }
                if any(row[k] > budget[k] or row[k] < 0 for k in METRICS):
                    raise ValueError("Observed budget exceeded: experiment incomplete")
                rows.append(row)
    result = evaluate(
        [{k: case[k] for k in ("id", "family", "regime", "split", "expected")} for case in frozen],
        rows, budget=budget, min_trials=trials)
    result["runner_schema"] = RUNNER_SCHEMA
    result["manifest_sha256"] = digest(manifest)
    result["operator_cards_sha256"] = digest(operator_cards)
    result["execution_status"] = "COMPLETED_UNCERTIFIED"
    result["tool_condition_limitation"] = (
        "No tool-use adapter is implemented. All four policies have identical tool access.")
    return {"runs": rows, "report": result}


class OpenAICompatibleAdapter:
    """Opt-in, no-tools chat-completions transport. Requires explicit endpoint/key.

    No automatic retries, no background execution, no agent tool access.
    Provider usage is self-reported and must be checked by a trusted meter.
    """
    def __init__(self, *, endpoint, model, api_key_env="OPENAI_API_KEY",
                 input_microusd_per_million=0, output_microusd_per_million=0):
        if not endpoint.startswith("https://") or not endpoint.endswith("/chat/completions"):
            raise ValueError("Explicit HTTPS chat-completions endpoint required")
        if not _valid_text(model):
            raise ValueError("Model required")
        if any(type(v) is not int or v < 0 for v in
               (input_microusd_per_million, output_microusd_per_million)):
            raise ValueError("Invalid model pricing")
        self.endpoint, self.model, self.key_env = endpoint, model, api_key_env
        self.input_rate, self.output_rate = input_microusd_per_million, output_microusd_per_million

    def __call__(self, payload):
        key = os.environ.get(self.key_env)
        if not key:
            raise ValueError("API key environment variable is missing")
        body = json.dumps({
            "model": self.model, "temperature": 0,
            "max_tokens": payload["max_output_tokens"],
            "messages": [
                {"role": "system", "content": payload["system"]},
                {"role": "user", "content": payload["prompt"]},
            ],
        }).encode("utf-8")
        req = request.Request(self.endpoint, data=body, method="POST",
                              headers={"Authorization": "Bearer " + key,
                                       "Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=60) as response:
                data = json.loads(response.read(2_000_000))
        except HTTPError as exc:
            raise ValueError("Provider request failed with HTTP " + str(exc.code)) from exc
        usage = data.get("usage", {})
        tokens_in, tokens_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if type(tokens_in) is not int or type(tokens_out) is not int:
            raise ValueError("Provider did not report usable token counts")
        raw = data["choices"][0]["message"]["content"]
        if not isinstance(raw, str):
            raise ValueError("Non-text completion unsupported")
        return {
            "output": raw.strip(), "tokens_in": tokens_in, "tokens_out": tokens_out,
            "cost_microusd": (
                tokens_in * self.input_rate + tokens_out * self.output_rate + 999999
            ) // 1000000,
            "model_id": self.model, "tools_fingerprint": "none-v1",
        }
