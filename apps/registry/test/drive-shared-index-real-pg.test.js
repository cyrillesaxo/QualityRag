// US-068: the shared Drive index against a real PostgreSQL, with two replicas (separate local index
// directories, separate pools) sharing only the encrypted checkpoint row. Covers the shared read
// adapters (status, visibility, search, governed candidates) and the drift/STALE paths that the
// in-memory SQL harness covered before. Drive itself is a local fake.
import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes, createHash} from 'node:crypto';
import {mkdtempSync, rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import pg from 'pg';
import {migrate} from '../src/migrate.js';
import {UserDriveIndex} from '../src/user-drive-index.js';
import {PgDriveCursorCoordinator} from '../src/pg-drive-cursor-coordinator.js';

const url = process.env.PG_TEST_DATABASE_URL;
const hash = (x) => createHash('sha256').update(x).digest('hex');
const NOW = Date.parse('2026-11-10T12:05:00Z');
const policySha = 'c'.repeat(64);
const policy = {id: 'release-readiness', version: '1', requirements: [{id: 'security_approval'}]};

function setup(pools) {
  const owner = `issuer#owner-${randomBytes(4).toString('hex')}`;
  const encryptionKey = randomBytes(32).toString('base64'), identityKey = randomBytes(32);
  const dirs = [];
  const replica = (pool) => {
    const dir = mkdtempSync(join(tmpdir(), 'qr-shared-index-')); dirs.push(dir);
    const coordinator = new PgDriveCursorCoordinator(pool, {identityKey});
    return {idx: new UserDriveIndex({dir, encryptionKey, cursorCoordinator: coordinator, now: () => NOW}), coordinator};
  };
  const A = replica(pools[0]), B = replica(pools[1]);
  const connection = {connected: true, email: 'owner@example.test', folderId: 'selected'};
  const lines = ['Security approval was signed on 3 November.', 'Payments are excluded unless the scan passes.'];
  const entry = (n, body) => ({fileId: `file-${n}`, revision: hash(body.join('\n')), mimeType: 'text/plain', name: `note-${n}.txt`,
    sourceId: 'google_drive/' + String(n).repeat(32).slice(0, 32), searchEnabled: true, lines: body});
  const snapshot = {schema: 'qualityrag.user-drive-text-index/v1', account: connection.email, folderId: connection.folderId,
    syncedAt: '2026-11-10T12:00:00Z', baselineId: `baseline-${randomBytes(4).toString('hex')}`,
    entries: [entry(1, lines), entry(2, ['Unrelated planning note.'])], coverage: 'SELECTED_FOLDER_TEXT_FILES', changePageToken: 'initial'};
  const connector = {status: () => ({...connection}), supportsText: (m) => m === 'text/plain',
    selectedFiles: async () => ({folderId: 'selected', truncated: false, files: snapshot.entries.map((e) => ({id: e.fileId, mimeType: 'text/plain'}))}),
    downloadSelectedText: async (_s, fileId) => Buffer.from(snapshot.entries.find((e) => e.fileId === fileId).lines.join('\n')),
    driveChangePage: async () => ({changes: [], nextPageToken: null, newStartPageToken: 'next'})};
  return {owner, A, B, connection, snapshot, connector, cleanup: () => dirs.forEach((d) => rmSync(d, {recursive: true, force: true}))};
}

test('US-068 shared index on real PostgreSQL: two replicas read one verified baseline', {skip: !url, timeout: 60000}, async (t) => {
  const pools = [new pg.Pool({connectionString: url, max: 4}), new pg.Pool({connectionString: url, max: 4})];
  try {
    await migrate(pools[0]);

    await t.test('replica B (no local index) reads the shared baseline; its local cache is never used', async () => {
      const f = setup(pools);
      try {
        await f.A.coordinator.establish(f.owner, f.snapshot, f.A.idx.encode(f.owner, {cursor: 'initial'}), f.A.idx.encode(f.owner, f.snapshot));
        const status = await f.B.idx.statusShared(f.owner, f.connection);
        assert.deepEqual([status.indexed, status.sourceCount, status.syncStatus, status.activityLogScope], [true, 2, 'READY', 'SHARED_ENCRYPTED_BASELINE']);
        assert.equal(f.B.idx.status(f.owner, f.connection).indexed, false, 'the local path sees nothing on B');
        const found = await f.B.idx.searchShared(f.owner, f.connection, 'security approval');
        assert.equal(found.hits.length, 1);
        assert.equal(found.hits[0].quality, 'LEXICAL_MATCH_NOT_EVIDENCE_ADMISSION');
        const vis = await f.B.idx.visibilityShared(f.owner, f.connection);
        assert.deepEqual(vis.sources.map((s) => s.searchable), [true, true]);
        const other = await f.B.idx.statusShared(f.owner, {...f.connection, email: 'someone-else@example.test'});
        assert.equal(other.indexed, false, 'a different account binding cannot read the baseline');
      } finally { f.cleanup(); }
    });

    await t.test('an owner exclusion on A is enforced on B even though the baseline is now STALE', async () => {
      const f = setup(pools);
      try {
        await f.A.coordinator.establish(f.owner, f.snapshot, f.A.idx.encode(f.owner, {cursor: 'initial'}), f.A.idx.encode(f.owner, f.snapshot));
        const excluded = f.snapshot.entries[0];
        await f.A.idx.controlSharedSource(f.owner, f.connection, {sourceId: excluded.sourceId, searchable: false, reason: 'SENSITIVE'});
        const status = await f.B.idx.statusShared(f.owner, f.connection);
        assert.equal(status.syncStatus, 'STALE', 'a control edit requires a resync before protected use');
        assert.equal(status.sourceControls.excluded, 1);
        const search = await f.B.idx.searchShared(f.owner, f.connection, 'security approval');
        assert.deepEqual([search.hits.length, search.reason], [0, 'SYNC_REQUIRED']);
        const check = await f.B.idx.checkGovernedCandidatesShared(f.owner, f.connection, policy, policySha,
          [{sourceId: excluded.sourceId, revision: excluded.revision, requirementId: 'security_approval', lineNumber: 1}]);
        assert.equal(check.result, 'REFUSE');
        assert.deepEqual(check.observations[0].reasons, ['SOURCE_EXCLUDED_BY_OWNER'], 'the denial is not hidden behind staleness');
        assert.equal(check.index.freshness, 'NOT_CURRENT');
      } finally { f.cleanup(); }
    });

    await t.test('a fresh, unexcluded candidate is eligible for review on B — and never admitted', async () => {
      const f = setup(pools);
      try {
        await f.A.coordinator.establish(f.owner, f.snapshot, f.A.idx.encode(f.owner, {cursor: 'initial'}), f.A.idx.encode(f.owner, f.snapshot));
        const e = f.snapshot.entries[0];
        const check = await f.B.idx.checkGovernedCandidatesShared(f.owner, f.connection, policy, policySha,
          [{sourceId: e.sourceId, revision: e.revision, requirementId: 'security_approval', lineNumber: 1}]);
        assert.deepEqual([check.result, check.evaluationAdmitted, check.observations[0].eligibleForReviewedEvidence], ['INCONCLUSIVE', false, true]);
      } finally { f.cleanup(); }
    });

    await t.test('drift inspection on real PostgreSQL: clean scan advances; a changed file persists STALE; then UNKNOWN', async () => {
      const f = setup(pools);
      try {
        await f.A.coordinator.establish(f.owner, f.snapshot, f.A.idx.encode(f.owner, {cursor: 'initial'}), f.A.idx.encode(f.owner, f.snapshot));
        assert.equal((await f.B.idx.inspectSelectedFolderDrift(f.owner, f.connector)).state, 'MATCHED_AT_CHECK_TIME');
        const cp = await f.A.coordinator.read(f.owner);
        assert.equal(f.A.idx.decode(f.owner, cp.encrypted_cursor).cursor, 'next', 'B advanced the shared cursor');
        f.connector.driveChangePage = async () => ({changes: [{fileId: 'file-1', removed: false, metadataAvailable: true, parents: ['selected']}],
          nextPageToken: null, newStartPageToken: 'later'});
        assert.equal((await f.A.idx.inspectSelectedFolderDrift(f.owner, f.connector)).state, 'CHANGED');
        assert.equal((await f.B.coordinator.read(f.owner)).stale, true);
        assert.equal((await f.B.idx.inspectSelectedFolderDrift(f.owner, f.connector)).state, 'UNKNOWN', 'STALE is never reclassified as current');
      } finally { f.cleanup(); }
    });
  } finally {
    await Promise.all(pools.map((p) => p.end()));
  }
});
