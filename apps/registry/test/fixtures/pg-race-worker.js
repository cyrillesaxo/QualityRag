// US-068: one worker process for the real two-process PostgreSQL race tests.
// Each worker owns its own pg Pool (a separate connection set, as a separate Registry replica would),
// prints READY, waits for the parent to release the barrier file, runs one operation and prints the
// JSON outcome. Keys arrive as base64 arguments so both workers share the same deployment secrets.
import fs from 'node:fs';
import pg from 'pg';
import {PgDriveCursorCoordinator} from '../../src/pg-drive-cursor-coordinator.js';
import {PgDriveOAuthPending} from '../../src/pg-drive-oauth-pending.js';
import {PgDriveOwnerCredentials} from '../../src/pg-drive-owner-credentials.js';

const [op, barrier, payloadJson] = process.argv.slice(2);
const payload = JSON.parse(payloadJson);
const identityKey = Buffer.from(payload.identityKey, 'base64');
const encryptionKey = Buffer.from(payload.encryptionKey, 'base64');
const pool = new pg.Pool({connectionString: process.env.PG_TEST_DATABASE_URL, max: 2});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const envelope = (ct) => ({v: 1, iv: 'iv', ct, tag: 'tag'});

async function run() {
  const cursor = new PgDriveCursorCoordinator(pool, {identityKey});
  const pending = new PgDriveOAuthPending(pool, {identityKey, encryptionKey});
  const creds = new PgDriveOwnerCredentials(pool, {identityKey, encryptionKey});
  await pool.query('SELECT 1'); // connect before the barrier so the race is on the operation itself
  process.stdout.write('READY\n');
  while (!fs.existsSync(barrier)) await sleep(2);
  if (payload.delayMs) await sleep(payload.delayMs); // lets a test fix which replica reaches the lock first
  switch (op) {
    case 'advance':
      return cursor.advance({subject: payload.subject, generation: payload.generation, binding: payload.binding,
        version: payload.version, encryptedCursor: envelope(`cursor-${payload.tag}`)});
    case 'replace':
      return cursor.replaceBaseline(payload.subject, payload.snapshot, envelope('cursor-new'), payload.expected, envelope('snapshot-new'));
    case 'stale':
      return cursor.markStale({subject: payload.subject, generation: payload.generation, binding: payload.binding});
    case 'consume':
      try { return {consumed: (await pending.consume(payload.state)).subject}; } catch (e) { return {error: e.message}; }
    case 'refresh': {
      const seen = [];
      try {
        const r = await creds.refreshLocked(payload.subject, async (current) => {
          seen.push(current.access_token);
          await sleep(payload.holdMs); // the Google token call happens while the row lock is held
          return {...current, access_token: `${current.access_token}+${payload.tag}`};
        });
        return {predecessor: seen[0], next: r.value.access_token};
      } catch (e) { return {error: e.message, predecessor: seen[0] ?? null}; }
    }
    default: throw new Error(`unknown op ${op}`);
  }
}
run().then((outcome) => { process.stdout.write(`${JSON.stringify({outcome})}\n`); }, (e) => { process.stdout.write(`${JSON.stringify({thrown: e.message})}\n`); })
  .finally(() => pool.end());
