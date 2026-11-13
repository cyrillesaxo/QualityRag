-- US-068: encrypted source baseline is atomically co-located with its Drive cursor.
-- Separate additive migration preserves the checksum of migration 012.
ALTER TABLE qr_drive_cursor_checkpoints
 ADD COLUMN IF NOT EXISTS encrypted_snapshot jsonb;
ALTER TABLE qr_drive_cursor_checkpoints
 ADD CONSTRAINT qr_drive_checkpoint_snapshot_object
 CHECK (encrypted_snapshot IS NULL OR jsonb_typeof(encrypted_snapshot)='object');
-- Existing rows with NULL snapshots are UNKNOWN until an authorized new sync.
