# Activation SDK and CLI parity

Python, TypeScript and the CLI use the same authenticated activation API and
canonical finite evaluator. JSON Schema validation checks shape; it does not
authorize semantic admission. A finite SAT receipt still has can_generate=false.

## External policy and source-backed requests

The host supplies an authenticated access envelope, an external reviewed PackSpec
ConstraintIR, and a publisher-signed compatibility manifest. The manifest must
bind the actual source and encoded artifact hashes, policy IR hash, tenant,
runtime and version policy. Upload the original source and the exact artifact
bytes through an authorized client before evaluation. A caller cannot choose a
different tenant, clock, signing key or minimum version in an API request.

The following Python example assumes those host-prepared files are available:

~~~python
import json
from pathlib import Path
from qualityrag_activation import Client, FiniteReceipt

load = lambda name: json.loads(Path(name).read_text())
client = Client("https://your-activation-host.example", load("access-token.json"))
source = client.upload(Path("original-source.json").read_bytes())
client.upload(Path("encoded-artifact.json").read_bytes())
request = {
    "source_sha256": source["source_sha256"],
    "artifact": load("encoded-artifact.json"),
    "signed_manifest": load("signed-manifest.json"),
    "policy_ir": load("external-policy-ir.json"),
}
receipt: FiniteReceipt = client.evaluate(**request)
assert receipt["can_generate"] is False
shape_check = client.validate("receipt", receipt)
trace = client.trace(**request)
original = client.fallback(source["source_sha256"])
~~~

Artifact upload must use the exact canonical bytes covered by the manifest;
reformatting JSON changes its content address. This example does not sign policy
or create independent review. The host must supply genuine authorized bindings.
The returned fallback contains authorized original bytes, never an unchecked
decoder's reconstructed output.

TypeScript exports ActivationClient, SignedEnvelope, FiniteReceipt,
ValidationResult and FallbackResult from the SDK entry point:

~~~typescript
const client = new ActivationClient(endpoint, token);
const receipt = await client.evaluate(request);
const shape = await client.validate("receipt", receipt);
const trace: string[] = await client.trace(request);
const original = await client.fallback(request.source_sha256);
~~~

## CLI operations

Put the same four request fields into request.json. The token file holds the
signed envelope, not a raw private key. Point --endpoint at the final configured
API endpoint; the clients refuse redirects, including redirects on the same host.

~~~bash
python -m tools.activation_runtime.cli validate receipt receipt.json
python -m tools.activation_runtime.cli evaluate --endpoint https://your-activation-host.example --token access-token.json --request request.json
python -m tools.activation_runtime.cli trace --endpoint https://your-activation-host.example --token access-token.json --request request.json
python -m tools.activation_runtime.cli fallback --endpoint https://your-activation-host.example --token access-token.json --source-sha256 SOURCE_SHA256
~~~

Trace returns the evaluator's actual ordered trace array. It performs the same
authenticated evaluation checks as evaluate. Validation reports valid=true and
semantic_admission=INCONCLUSIVE consistently across all three interfaces.
Unsupported options are refused rather than silently discarded.

## Transport contract and verification

Both SDKs accept explicit loopback HTTP or a host-selected HTTPS endpoint. URL
userinfo, query strings, fragments and control characters are refused. Redirects
cannot forward the signed bearer envelope to another endpoint. Python timeouts
must be finite, positive and at most 60 seconds; its default and the TypeScript
request timeout are 10 seconds. TypeScript refuses undefined, nonfinite numbers,
functions, symbols and bigint values instead of silently changing their JSON
representation. Python also refuses nonfinite JSON numbers.

Actual HTTP golden tests compare validate/evaluate/trace/fallback across Python,
TypeScript and CLI for exact reconstruction and a signed artifact that drops NOT.
The latter must return UNSAT/REFUSE, no research output and can_generate=false.
Separate real-server tests check redirects receive no request, unsupported
options refuse and a foreign tenant cannot fetch the source. No cloud account,
paid provider or production key is needed for these authored engineering tests.

~~~bash
python -m unittest discover -s tools/activation_runtime/tests -p 'test_service_sdk.py' -v
cd sdk/typescript
npm test
~~~
