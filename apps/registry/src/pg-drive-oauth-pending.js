import {createHmac,createCipheriv,createDecipheriv,randomBytes} from 'node:crypto';

const fail=message=>{throw Error(message)};
const check=(condition,message)=>{if(!condition)fail(message)};
const STATE=/^[A-Za-z0-9_-]{30,120}$/;
export class PgDriveOAuthPending {
 constructor(pool,{identityKey,encryptionKey,now=()=>Date.now()}={}){
  check(pool&&typeof pool.query==='function','DRIVE_OAUTH_PENDING_POOL_REQUIRED');
  check(Buffer.isBuffer(identityKey)&&identityKey.length===32&&
    Buffer.isBuffer(encryptionKey)&&encryptionKey.length===32,
    'DRIVE_OAUTH_PENDING_KEYS_REQUIRED');
  check(!identityKey.equals(encryptionKey),'DRIVE_OAUTH_PENDING_KEY_SEPARATION');
  this.pool=pool;this.key=identityKey;this.encryptionKey=encryptionKey;this.now=now;
 }
 selector(state){
  check(typeof state==='string'&&STATE.test(state),'DRIVE_OAUTH_STATE_INVALID');
  return createHmac('sha256',this.key).update('qualityrag.drive-oauth-state/v1:'+state)
    .digest('hex');
 }
 seal(state,pending){
  check(typeof pending?.subject==='string'&&pending.subject.trim()&&
    typeof pending.verifier==='string'&&pending.verifier.length>=40,
    'DRIVE_OAUTH_STATE_INVALID');
  const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',this.encryptionKey,iv);
  cipher.setAAD(Buffer.from('qualityrag.drive-oauth-pending/v1:'+state));
  const payload=Buffer.concat([cipher.update(JSON.stringify(pending),'utf8'),cipher.final()]);
  return {v:1,iv:iv.toString('base64url'),ct:payload.toString('base64url'),
    tag:cipher.getAuthTag().toString('base64url')};
 }
 open(state,encrypted){
  try{
   check(encrypted?.v===1,'DRIVE_OAUTH_STATE_INVALID');
   const decipher=createDecipheriv('aes-256-gcm',this.encryptionKey,
     Buffer.from(encrypted.iv,'base64url'));
   decipher.setAAD(Buffer.from('qualityrag.drive-oauth-pending/v1:'+state));
   decipher.setAuthTag(Buffer.from(encrypted.tag,'base64url'));
   const result=JSON.parse(Buffer.concat([
     decipher.update(Buffer.from(encrypted.ct,'base64url')),
     decipher.final()
   ]).toString('utf8'));
   check(typeof result.subject==='string'&&result.subject.trim()&&
     typeof result.verifier==='string'&&result.verifier.length>=40,
     'DRIVE_OAUTH_STATE_INVALID');
   return result;
  }catch{fail('DRIVE_OAUTH_STATE_INVALID')}
 }
 async issue(state,pending){
  const expires=this.now()+600_000;
  const result=await this.pool.query(`
    INSERT INTO qr_drive_oauth_pending(state_key,encrypted_pending,expires_at)
    VALUES($1,$2::jsonb,to_timestamp($3/1000.0))
    ON CONFLICT DO NOTHING RETURNING state_key
  `,[this.selector(state),JSON.stringify(this.seal(state,pending)),expires]);
  check(result.rowCount===1,'DRIVE_OAUTH_STATE_INVALID');
  return {expiresAt:expires};
 }
 async consume(state){
  // DELETE RETURNING enforces one-time use even across independent replicas.
  // Expired states are deleted too: do not leave an invalid replayable row.
  const result=await this.pool.query(`
    DELETE FROM qr_drive_oauth_pending WHERE state_key=$1
    RETURNING encrypted_pending,(expires_at > now()) AS valid
  `,[this.selector(state)]);
  check(result.rowCount===1&&result.rows[0].valid===true,
    'DRIVE_OAUTH_STATE_INVALID');
  return this.open(state,result.rows[0].encrypted_pending);
 }
 async purgeExpired(){
  const result=await this.pool.query(
    'DELETE FROM qr_drive_oauth_pending WHERE expires_at <= now()');
  return result.rowCount;
 }
}
