-- Metadata-only review requests. Source and premise are resolved from the
-- authorized source system, not copied into this queue.
CREATE TABLE qr_guided_question_requests (
 request_id text PRIMARY KEY CHECK(request_id ~ '^[a-f0-9]{64}$'),
 owner_binding text NOT NULL CHECK(owner_binding ~ '^[a-f0-9]{64}$'),
 service_id text NOT NULL CHECK(service_id ~ '^[A-Za-z0-9._:-]{1,128}$'),
 environment text NOT NULL CHECK(environment ~ '^[A-Za-z0-9._:-]{1,128}$'),
 policy_digest text NOT NULL CHECK(policy_digest ~ '^[a-f0-9]{64}$'),
 target_digest text NOT NULL CHECK(target_digest ~ '^[a-f0-9]{64}$'),
 target_id text NOT NULL CHECK(target_id ~ '^[A-Za-z0-9._:-]{1,128}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(owner_binding,service_id,environment,policy_digest,target_digest,target_id)
);
CREATE INDEX qr_guided_question_request_scope
 ON qr_guided_question_requests(owner_binding,service_id,environment,created_at,request_id);
CREATE INDEX qr_guided_question_receipt_target
 ON qr_guided_question_receipts(owner_binding,service_id,environment,policy_digest,target_digest,recorded_at DESC,receipt_digest);
REVOKE ALL ON qr_guided_question_requests FROM PUBLIC;
-- No approval column: decisions remain in the existing signed receipt ledger.
-- No public queue, reviewer assignment or retention policy is activated here.
