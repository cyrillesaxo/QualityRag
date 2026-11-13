// US-068: real two-process PostgreSQL acceptance for the shared Drive coordination.
// Every race below is run by two separate OS processes, each with its own pg Pool (as two Registry
// replicas would be), released together through a barrier file against a real PostgreSQL database.
// Skipped when PG_TEST_DATABASE_URL is not set (CI sets it). This is not Google Drive acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {randomBytes} from 'node:crypto';
import pg from 'pg';
import {migrate} from '../src/migrate.js';
import {PgDriveCursorCoordinator} from '../src/pg-drive-cursor-coordinator.js';
import {PgDriveOAuthPending} from '../src/pg-drive-oauth-pending.js';
import {PgDriveOwnerCredentials} from '../src/pg-drive-owner-credentials.js';

const url = process.env.PG_TEST_DATABASE_URL;
const WORKER = new URL('./fixtures/pg-race-worker.js', import.meta.url).pathname;
const identityKey = randomBytes(32), encryptionKey = randomBytes(32);
const keys = {identityKey: identityKey.toString('base64'), encryptionKey: encryptionKey.toString('base64')};
const envelope = (ct) => ({v: 1, iv: 'iv', ct, tag: 'tag'});
const snapshot = (n) => ({syncedAt: `2026-11-13T00:00:0${n}.000Z`, folderId: 'folder-a', account: 'owner@example.test', entries: [{fileId: 'f', revision: `r${n}`}]});

/** Start one worker per op, wait until all are connected, release them together, collect outcomes. */
async function race(ops) {
  const barrier = path.join(os.tmpdir(), `qr-barrier-${randomBytes(6).toString('hex')}`);
  const procs = ops.map(([op, payload]) => {
    const child = spawn(process.execPath, [WORKER, op, barrier, JSON.stringify({...keys, ...payload})], {env: process.env, stdio: ['ignore', 'pipe', 'pipe']});
    let out = '', err = '';
    child.stdout.on('data', (d) => { out += d; });
    child.stderr.on('data', (d) => { err += d; });
    const ready = new Promise((resolve, reject) => {
      const t = setInterval(() => { if (out.includes('READY')) { clearInterval(t); resolve(); } }, 5);
      child.on('exit', () => { clearInterval(t); if (!out.includes('READY')) reject(new Error(`worker failed: ${err}`)); });
    });
    const done = new Promise((resolve) => child.on('exit', () => {
      const line = out.split('\n').find((l) => l.startsWith('{'));
      resolve(line ? JSON.parse(line) : {thrown: err || 'no output'});
    }));
    return {ready, done, pid: child.pid};
  });
  await Promise.all(procs.map((p) => p.ready));
  assert.equal(new Set(procs.map((p) => p.pid)).size, ops.length, 'separate OS processes');
  fs.writeFileSync(barrier, 'go');
  try { return await Promise.all(procs.map((p) => p.done)); } finally { fs.rmSync(barrier, {force: true}); }
}

test('US-068 two-process PostgreSQL: cursor CAS, fenced resync, irreversible STALE, one-time OAuth state, serialised refresh',
  {skip: !url, timeout: 60000}, async (t) => {
    const pool = new pg.Pool({connectionString: url, max: 4});
    try {
      await migrate(pool);
      const cursor = new PgDriveCursorCoordinator(pool, {identityKey});

      await t.test('two replicas advance the same cursor version: exactly one wins', async () => {
        const subject = `issuer#race-${randomBytes(4).toString('hex')}`;
        const {generation, binding} = await cursor.establish(subject, snapshot(1), envelope('c0'), envelope('s0'));
        for (let round = 0; round < 5; round++) {
          const version = Number((await cursor.read(subject)).cursor_version);
          const outcomes = await race([['advance', {subject, generation, binding, version, tag: 'a'}], ['advance', {subject, generation, binding, version, tag: 'b'}]]);
          assert.deepEqual(outcomes.map((o) => o.outcome).sort(), ['ADVANCED', 'CONFLICT'], JSON.stringify(outcomes));
          assert.equal(Number((await cursor.read(subject)).cursor_version), version + 1);
        }
      });

      await t.test('a resync replacing the baseline fences an in-flight poll of the old generation', async () => {
        const subject = `issuer#resync-${randomBytes(4).toString('hex')}`;
        const {generation, binding} = await cursor.establish(subject, snapshot(1), envelope('c0'), envelope('s0'));
        const expected = await cursor.read(subject);
        const outcomes = await race([
          ['replace', {subject, snapshot: snapshot(2), expected: {generation, binding_digest: binding, cursor_version: Number(expected.cursor_version)}}],
          ['advance', {subject, generation, binding, version: Number(expected.cursor_version), tag: 'old-poll'}],
        ]);
        const [replaced, advanced] = outcomes.map((o) => o.outcome);
        assert.ok(!(replaced === 'REPLACED' && advanced === 'ADVANCED'), 'both cannot commit against the same version');
        assert.ok(replaced === 'REPLACED' || advanced === 'ADVANCED');
        const after = await cursor.read(subject);
        if (replaced === 'REPLACED') {
          assert.notEqual(after.generation, generation);
          assert.equal(await cursor.advance({subject, generation, binding, version: Number(after.cursor_version), encryptedCursor: envelope('late')}), 'CONFLICT',
            'an old-generation poll can never write after the resync');
        }
      });

      await t.test('STALE is irreversible: a racing advance cannot clean it, and no later advance succeeds', async () => {
        const subject = `issuer#stale-${randomBytes(4).toString('hex')}`;
        const {generation, binding} = await cursor.establish(subject, snapshot(1), envelope('c0'), envelope('s0'));
        const version = Number((await cursor.read(subject)).cursor_version);
        const outcomes = await race([['stale', {subject, generation, binding}], ['advance', {subject, generation, binding, version, tag: 'x'}]]);
        assert.equal(outcomes[0].outcome, 'STALE');
        const after = await cursor.read(subject);
        assert.equal(after.stale, true);
        assert.equal(await cursor.advance({subject, generation, binding, version: Number(after.cursor_version), encryptedCursor: envelope('y')}), 'CONFLICT');
        assert.equal(await cursor.markStale({subject, generation, binding}), 'STALE', 'idempotent');
      });

      await t.test('an OAuth state routed to two replicas is consumed exactly once', async () => {
        const pending = new PgDriveOAuthPending(pool, {identityKey, encryptionKey});
        const state = randomBytes(32).toString('base64url');
        await pending.issue(state, {subject: 'issuer#alice', verifier: randomBytes(32).toString('base64url')});
        const outcomes = await race([['consume', {state}], ['consume', {state}]]);
        const won = outcomes.filter((o) => o.outcome?.consumed === 'issuer#alice');
        const lost = outcomes.filter((o) => o.outcome?.error === 'DRIVE_OAUTH_STATE_INVALID');
        assert.deepEqual([won.length, lost.length], [1, 1], JSON.stringify(outcomes));
      });

      await t.test('two replicas refreshing the same credential are serialised: no predecessor is used twice', async () => {
        const creds = new PgDriveOwnerCredentials(pool, {identityKey, encryptionKey});
        const subject = `issuer#refresh-${randomBytes(4).toString('hex')}`;
        const start = await creds.authorize(subject, {access_token: 't0', refresh_token: 'r0', expires_at: 1, email: 'owner@example.test',
          display_name: 'Owner', folder_id: 'folder-a', folder_name: 'A'});
        const outcomes = await race([['refresh', {subject, holdMs: 400, tag: 'a'}], ['refresh', {subject, holdMs: 400, tag: 'b'}]]);
        assert.ok(outcomes.every((o) => o.outcome && !o.outcome.error), JSON.stringify(outcomes));
        const predecessors = outcomes.map((o) => o.outcome.predecessor);
        assert.equal(new Set(predecessors).size, 2, `each refresh saw a different predecessor: ${predecessors}`);
        assert.ok(predecessors.includes('t0'));
        const final = await creds.get(subject);
        assert.equal(final.revision, start + 2);
        assert.ok(['t0+a+b', 't0+b+a'].includes(final.value.access_token), final.value.access_token);
      });

      await t.test('a refresh held past the lock timeout fails closed instead of using a stale predecessor', async () => {
        const creds = new PgDriveOwnerCredentials(pool, {identityKey, encryptionKey});
        const subject = `issuer#slow-${randomBytes(4).toString('hex')}`;
        await creds.authorize(subject, {access_token: 't0', refresh_token: 'r0', expires_at: 1, email: 'owner@example.test',
          display_name: 'Owner', folder_id: 'folder-a', folder_name: 'A'});
        // The slow replica takes the row lock first and holds it through a 4.5 s provider call.
        const outcomes = await race([['refresh', {subject, holdMs: 4500, tag: 'slow'}], ['refresh', {subject, holdMs: 0, tag: 'fast', delayMs: 300}]]);
        const failed = outcomes.filter((o) => o.outcome?.error);
        const ok = outcomes.filter((o) => o.outcome && !o.outcome.error);
        assert.equal(ok.length, 1, JSON.stringify(outcomes));
        assert.equal(failed.length, 1, 'the waiting replica times out (lock_timeout 3 s) rather than rotating a stale token');
        assert.equal(ok[0].outcome.next, 't0+slow');
        assert.match(failed[0].outcome.error, /lock timeout/i);
        assert.equal(failed[0].outcome.predecessor, null, 'the timed-out replica never saw a credential');
        assert.equal((await creds.get(subject)).value.access_token, ok[0].outcome.next);
      });

      await t.test('disconnect during refresh: the tombstone wins and refresh cannot resurrect the credential', async () => {
        const creds = new PgDriveOwnerCredentials(pool, {identityKey, encryptionKey});
        const subject = `issuer#disc-${randomBytes(4).toString('hex')}`;
        await creds.authorize(subject, {access_token: 't0', refresh_token: 'r0', expires_at: 1, email: 'owner@example.test',
          display_name: 'Owner', folder_id: 'folder-a', folder_name: 'A'});
        assert.equal(await creds.disconnect(subject), true);
        const [o] = await race([['refresh', {subject, holdMs: 0, tag: 'z'}]]);
        assert.equal(o.outcome.error, 'DRIVE_CONNECTION_NOT_FOUND');
        assert.equal(await creds.get(subject), null);
      });
    } finally {
      await pool.end();
    }
  });
