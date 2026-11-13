// US-068: two Registry replicas (separate connector instances, separate local credential files and
// separate PostgreSQL pools) sharing only the PostgreSQL OAuth state and owner credentials.
// Google is a local fake; this proves cross-replica coherence, not live Google Drive behaviour.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {randomBytes} from 'node:crypto';
import pg from 'pg';
import {migrate} from '../src/migrate.js';
import {GoogleDriveConnections} from '../src/google-drive-connections.js';
import {PgDriveOAuthPending} from '../src/pg-drive-oauth-pending.js';
import {PgDriveOwnerCredentials} from '../src/pg-drive-owner-credentials.js';

const url = process.env.PG_TEST_DATABASE_URL;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function fakeGoogle() {
  const calls = {exchange: 0, refresh: 0, revoke: 0};
  let issued = 0;
  const json = (body, status = 200) => ({ok: status < 400, status, text: async () => JSON.stringify(body)});
  const fetchImpl = async (target, init = {}) => {
    const u = new URL(target);
    if (u.href.startsWith('https://oauth2.googleapis.com/token')) {
      const form = new URLSearchParams(init.body);
      if (form.get('grant_type') === 'authorization_code') {
        calls.exchange++;
        return json({access_token: `access-initial-${'x'.repeat(24)}`, refresh_token: `refresh-${'y'.repeat(24)}`, expires_in: 3600,
          scope: 'https://www.googleapis.com/auth/drive.readonly'});
      }
      calls.refresh++;
      await sleep(150); // provider latency while the owner row is locked
      issued++;
      return json({access_token: `access-rotated-${issued}-${'z'.repeat(20)}`, expires_in: 3600});
    }
    if (u.href.startsWith('https://oauth2.googleapis.com/revoke')) { calls.revoke++; return json({}); }
    if (u.pathname.endsWith('/about')) return json({user: {emailAddress: 'owner@example.test', displayName: 'Owner'}});
    const folder = u.pathname.match(/\/files\/([A-Za-z0-9_-]+)$/);
    if (folder) return json({id: folder[1], name: 'Release evidence', mimeType: 'application/vnd.google-apps.folder', trashed: false});
    return json({error: 'unexpected'}, 500);
  };
  return {fetchImpl, calls};
}

function replica(pool, keys, google, clock) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'qr-replica-'));
  const file = path.join(dir, 'google-credentials.json');
  const oauthPending = new PgDriveOAuthPending(pool, {identityKey: keys.identity, encryptionKey: keys.encryption});
  const credentialStore = new PgDriveOwnerCredentials(pool, {identityKey: keys.identity, encryptionKey: keys.encryption});
  const manager = new GoogleDriveConnections({file, encryptionKey: keys.encryption.toString('base64'), clientId: 'client-id-for-tests.apps',
    clientSecret: 'client-secret-for-tests', redirectUri: 'https://registry.example.test/v1/drives/google/callback',
    studioOrigin: 'https://studio.example.test', fetchImpl: google.fetchImpl, now: clock, oauthPending, credentialStore});
  return {manager, file};
}

test('US-068 shared credentials: two replicas behave as one connection', {skip: !url, timeout: 60000}, async (t) => {
  const pools = [new pg.Pool({connectionString: url, max: 4}), new pg.Pool({connectionString: url, max: 4})];
  try {
    await migrate(pools[0]);
    const keys = {identity: randomBytes(32), encryption: randomBytes(32)};
    let now = Date.parse('2026-11-13T10:00:00Z');
    const clock = () => now;
    const google = fakeGoogle();
    const A = replica(pools[0], keys, google, clock), B = replica(pools[1], keys, google, clock);
    const subject = `issuer#owner-${randomBytes(4).toString('hex')}`;

    await t.test('connect started on A completes on B; A sees the connection; no local credential file', async () => {
      const started = await A.manager.startCoordinated(subject);
      const state = new URL(started.authorizationUrl).searchParams.get('state');
      const done = await B.manager.callback({state, code: 'approved-code'});
      assert.equal(done.subject, subject);
      const status = await A.manager.status(subject);
      assert.deepEqual([status.connected, status.email, status.folderId], [true, 'owner@example.test', null]);
      assert.equal(fs.existsSync(A.file) || fs.existsSync(B.file), false, 'credentials never touch the local file');
      await assert.rejects(B.manager.callback({state, code: 'approved-code'}), /DRIVE_OAUTH_STATE_INVALID/, 'state is one-time');
    });

    await t.test('a folder selected on B is the folder on A', async () => {
      const result = await B.manager.selectFolder(subject, 'folder-123');
      assert.equal(result.folderId, 'folder-123');
      const status = await A.manager.status(subject);
      assert.deepEqual([status.folderId, status.folderName], ['folder-123', 'Release evidence']);
    });

    await t.test('an expired token refreshed concurrently on both replicas rotates once at Google', async () => {
      now += 2 * 3600 * 1000; // the initial access token has expired
      const before = google.calls.refresh;
      const [ta, tb] = await Promise.all([A.manager.getToken(subject), B.manager.getToken(subject)]);
      assert.equal(google.calls.refresh - before, 1, 'the waiting replica reused the rotated token');
      assert.equal(ta, tb);
      assert.match(ta, /^access-rotated-/);
      const status = await B.manager.status(subject);
      assert.equal(status.folderId, 'folder-123', 'rotation never changes the folder');
    });

    await t.test('disconnect on A stops B at once; refresh cannot resurrect it; re-consent can', async () => {
      const out = await A.manager.disconnect(subject);
      assert.equal(out.connected, false);
      assert.equal((await B.manager.status(subject)).connected, false);
      await assert.rejects(B.manager.getToken(subject), /DRIVE_CONNECTION_NOT_FOUND/);
      await assert.rejects(B.manager.selectFolder(subject, 'folder-123'), /DRIVE_CONNECTION_NOT_FOUND/);
      assert.equal(google.calls.revoke, 1);
      const started = await B.manager.startCoordinated(subject);
      await A.manager.callback({state: new URL(started.authorizationUrl).searchParams.get('state'), code: 'approved-code'});
      const status = await B.manager.status(subject);
      assert.deepEqual([status.connected, status.folderId], [true, null], 're-consent reconnects without the old folder');
    });

    await t.test('shared credentials require shared OAuth state', () => {
      assert.throws(() => new GoogleDriveConnections({file: path.join(os.tmpdir(), 'x.json'), encryptionKey: keys.encryption.toString('base64'),
        clientId: 'client-id-for-tests.apps', clientSecret: 'client-secret-for-tests', redirectUri: 'https://registry.example.test/v1/drives/google/callback',
        studioOrigin: 'https://studio.example.test', credentialStore: {}}), /DRIVE_SHARED_CREDENTIALS_REQUIRE_SHARED_OAUTH_STATE/);
    });
  } finally {
    await Promise.all(pools.map((p) => p.end()));
  }
});
