import {createHmac} from 'node:crypto';

// Shared transactional coordinator; requires the already-operated Registry PG pool.
// Caller encrypts the Google cursor using UserDriveIndex.encode and supplies only
// keyed identities/generations. This class never sees an OAuth token or plaintext cursor.
const hex=/^[a-f0-9]{64}$/;
const valid=x=>typeof x==='string'&&hex.test(x);
const ensure=(x,msg)=>{if(!x)throw Error(msg)};
export class PgDriveCursorCoordinator {
 constructor(pool,{identityKey}={}){
  ensure(pool&&typeof pool.query==='function','CURSOR_POOL_REQUIRED');
  ensure(Buffer.isBuffer(identityKey)&&identityKey.length===32,'CURSOR_IDENTITY_KEY_REQUIRED');
  this.pool=pool;this.key=identityKey;
 }
 digest(label,value){
  ensure(typeof value==='string'&&value.length>0&&value.length<=1200,'CURSOR_IDENTITY_INVALID');
  return createHmac('sha256',this.key).update(label+'\0'+value).digest('hex');
 }
 owner(subject){return this.digest('owner/v1',subject)}
 generation(subject,snapshot){
  return this.digest('baseline/v1',subject+'\0'+snapshot.syncedAt+'\0'+snapshot.folderId+
    '\0'+snapshot.account+'\0'+(snapshot.entries||[]).map(e=>e.fileId+':'+e.revision).join('|'));
 }
 binding(subject,connection){
  return this.digest('binding/v1',subject+'\0'+connection.email+'\0'+connection.folderId);
 }
 async establish(subject,snapshot,encryptedCursor){
  ensure(snapshot&&snapshot.syncedAt&&snapshot.folderId&&snapshot.account,'CURSOR_BASELINE_REQUIRED');
  ensure(encryptedCursor&&encryptedCursor.v===1&&typeof encryptedCursor.ct==='string',
    'CURSOR_CIPHERTEXT_REQUIRED');
  const owner=this.owner(subject),generation=this.generation(subject,snapshot);
  const binding=this.binding(subject,{email:snapshot.account,folderId:snapshot.folderId});
  await this.pool.query(`
   INSERT INTO qr_drive_cursor_checkpoints
    (owner_key,generation,binding_digest,cursor_version,encrypted_cursor,stale)
   VALUES ($1,$2,$3,0,$4::jsonb,false)
   ON CONFLICT (owner_key) DO UPDATE SET
    generation=EXCLUDED.generation,binding_digest=EXCLUDED.binding_digest,
    cursor_version=qr_drive_cursor_checkpoints.cursor_version+1,
    encrypted_cursor=EXCLUDED.encrypted_cursor,stale=false,updated_at=now()
  `,[owner,generation,binding,JSON.stringify(encryptedCursor)]);
  return {generation,binding};
 }
 async read(subject){
  const result=await this.pool.query(
   'SELECT generation,binding_digest,cursor_version,encrypted_cursor,stale FROM qr_drive_cursor_checkpoints WHERE owner_key=$1',
   [this.owner(subject)]);
  return result.rows[0]||null;
 }
 async advance({subject,generation,binding,version,encryptedCursor}){
  ensure(valid(generation)&&valid(binding)&&Number.isSafeInteger(version)&&version>=0,
    'CURSOR_EXPECTATION_INVALID');
  ensure(encryptedCursor?.v===1&&typeof encryptedCursor.ct==='string',
    'CURSOR_CIPHERTEXT_REQUIRED');
  const result=await this.pool.query(`
   UPDATE qr_drive_cursor_checkpoints SET
     cursor_version=cursor_version+1,encrypted_cursor=$6::jsonb,updated_at=now()
   WHERE owner_key=$1 AND generation=$2 AND binding_digest=$3
     AND cursor_version=$4 AND stale=false AND $5=true
   RETURNING cursor_version
  `,[this.owner(subject),generation,binding,version,true,JSON.stringify(encryptedCursor)]);
  return result.rowCount===1?'ADVANCED':'CONFLICT';
 }
 async markStale({subject,generation,binding}){
  ensure(valid(generation)&&valid(binding),'CURSOR_EXPECTATION_INVALID');
  const result=await this.pool.query(`
   UPDATE qr_drive_cursor_checkpoints SET stale=true,cursor_version=cursor_version+1,
     updated_at=now()
   WHERE owner_key=$1 AND generation=$2 AND binding_digest=$3 AND stale=false
   RETURNING cursor_version
  `,[this.owner(subject),generation,binding]);
  if(result.rowCount===1)return 'STALE';
  const current=await this.read(subject);
  return current&&current.generation===generation&&current.binding_digest===binding&&
    current.stale===true?'STALE':'CONFLICT';
 }
}
