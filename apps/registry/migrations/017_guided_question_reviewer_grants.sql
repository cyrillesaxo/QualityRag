-- Scoped reviewer grants for the guided question verifier.
-- Provision/revoke through a separately authorized administrative process.
CREATE TABLE IF NOT EXISTS qr_guided_question_reviewer_grants (
 reviewer_id text NOT NULL CHECK (reviewer_id ~ '^[A-Za-z0-9._:-]{1,128}$'),
 owner_binding text NOT NULL CHECK (owner_binding ~ '^[a-f0-9]{64}$'),
 service_id text NOT NULL,
 environment text NOT NULL,
 policy_digest text NOT NULL CHECK (policy_digest ~ '^[a-f0-9]{64}$'),
 public_key_pem text NOT NULL CHECK (length(public_key_pem) BETWEEN 1 AND 2048),
 grant_version bigint NOT NULL DEFAULT 1 CHECK (grant_version > 0),
 revoked_at timestamptz,
 PRIMARY KEY(reviewer_id,owner_binding,service_id,environment,policy_digest)
);
REVOKE ALL ON qr_guided_question_reviewer_grants FROM PUBLIC;
-- Any update (including key rotation or reactivation) invalidates old snapshots.
CREATE OR REPLACE FUNCTION qr_guided_question_bump_grant() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 NEW.grant_version := OLD.grant_version + 1;
 RETURN NEW;
END;
$$;
CREATE TRIGGER qr_guided_question_grant_version
 BEFORE UPDATE ON qr_guided_question_reviewer_grants
 FOR EACH ROW EXECUTE FUNCTION qr_guided_question_bump_grant();
