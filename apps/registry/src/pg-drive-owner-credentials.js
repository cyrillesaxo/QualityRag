import {createHmac,createCipheriv,createDecipheriv,randomBytes} from 'node:crypto';

const fail=message=>{throw Error(message)};
const requireValid=(condition,message)=>{if(!condition)fail(message)};
const validKey=key=>Buffer.isBuffer(key)&&key.length===32;
const authFields=['access_token','refresh_token','expires_at','email',
 'display_name','folder_id','folder_name'];

export class PgDriveOwnerCredentials {
 constructor(pool,{identityKey,encryptionKey}={}){
  requireValid(pool&&typeof pool.connect==='function','DRIVE_CREDENTIAL_POOL_REQUIRED');
  requireValid(validKey(identityKey)&&validKey(encryptionKey),
    'DRIVE_CREDENTIAL_KEYS_REQUIRED');
  requireValid(!identityKey.equals(encryptionKey),'DRIVE_CREDENTIAL_KEY_SEPARATION_REQUIRED');
  this.pool=pool;this.identityKey=identityKey;this.encryptionKey=encryptionKey;
 }
 owner(subject){
  requireValid(typeof subject==='string'&&subject.length>1&&subject.length<=300,
    'DRIVE_AUTHENTICATED_SUBJECT_REQUIRED');
  return createHmac('sha256',this.identityKey)
    .update('qualityrag.drive-credential-owner/v1:'+subject).digest('hex');
 }
 seal(subject,value){
  requireValid(value&&authFields.every(field=>Object.hasOwn(value,field)),
    'DRIVE_CREDENTIAL_INVALID');
  const iv=randomBytes(12),cipher=createCipheriv('aes-256-gcm',this.encryptionKey,iv);
  cipher.setAAD(Buffer.from('qualityrag.drive-credential/v1:'+subject));
  const data=Buffer.concat([cipher.update(JSON.stringify(value),'utf8'),cipher.final()]);
  return {v:1,iv:iv.toString('base64url'),ct:data.toString('base64url'),
    tag:cipher.getAuthTag().toString('base64url')};
 }
 open(subject,envelope){
  try{
   requireValid(envelope?.v===1&&typeof envelope.iv==='string'&&
     typeof envelope.ct==='string'&&typeof envelope.tag==='string',
     'DRIVE_CREDENTIAL_INTEGRITY_FAILURE');
   const decipher=createDecipheriv('aes-256-gcm',this.encryptionKey,
     Buffer.from(envelope.iv,'base64url'));
   decipher.setAAD(Buffer.from('qualityrag.drive-credential/v1:'+subject));
   decipher.setAuthTag(Buffer.from(envelope.tag,'base64url'));
   const value=JSON.parse(Buffer.concat([
     decipher.update(Buffer.from(envelope.ct,'base64url')),decipher.final()
   ]).toString('utf8'));
   requireValid(value&&authFields.every(field=>Object.hasOwn(value,field)),
     'DRIVE_CREDENTIAL_INTEGRITY_FAILURE');
   return value;
  }catch{fail('DRIVE_CREDENTIAL_INTEGRITY_FAILURE')}
 }
 async get(subject){
  const result=await this.pool.query(
    'SELECT revision,credential_envelope,disconnected FROM qr_drive_owner_credentials WHERE owner_key=$1',
    [this.owner(subject)]);
  if(!result.rowCount||result.rows[0].disconnected)return null;
  const row=result.rows[0];
  return {revision:Number(row.revision),value:this.open(subject,row.credential_envelope)};
 }
 // Explicit new owner authorization supersedes previous refresh credentials.
 // It increments revision and preserves a tombstone until the user reconnects.
 async authorize(subject,value){
  const result=await this.pool.query(`
    INSERT INTO qr_drive_owner_credentials
      (owner_key,revision,credential_envelope,disconnected)
    VALUES ($1,1,$2::jsonb,false)
    ON CONFLICT (owner_key) DO UPDATE SET
      revision=qr_drive_owner_credentials.revision+1,
      credential_envelope=EXCLUDED.credential_envelope,
      disconnected=false,updated_at=now()
    RETURNING revision
  `,[this.owner(subject),JSON.stringify(this.seal(subject,value))]);
  return Number(result.rows[0].revision);
 }
 // For a refresh, lock the owner row THROUGH the bounded Google network call.
 // This prevents two replicas from rotating tokens using the same predecessor.
 // No automatic upsert: disconnect/re-consent cannot be resurrected by refresh.
 async refreshLocked(subject,refresh){
  requireValid(typeof refresh==='function','DRIVE_REFRESH_CALLBACK_REQUIRED');
  const db=await this.pool.connect();let began=false;
  try{
   await db.query('BEGIN');began=true;
   await db.query("SET LOCAL lock_timeout = '3000ms'");
   await db.query("SET LOCAL statement_timeout = '15000ms'");
   const current=await db.query(`
     SELECT revision,credential_envelope,disconnected
     FROM qr_drive_owner_credentials WHERE owner_key=$1 FOR UPDATE
   `,[this.owner(subject)]);
   requireValid(current.rowCount===1&&!current.rows[0].disconnected,
     'DRIVE_CONNECTION_NOT_FOUND');
   const value=this.open(subject,current.rows[0].credential_envelope);
   const next=await refresh({...value});
   requireValid(next&&authFields.every(field=>Object.hasOwn(next,field)),
     'DRIVE_CREDENTIAL_INVALID');
   // Refresh cannot replace the account or folder association.
   requireValid(next.email===value.email&&next.folder_id===value.folder_id,
     'DRIVE_REFRESH_BINDING_CHANGED');
   await db.query(`
     UPDATE qr_drive_owner_credentials SET
       credential_envelope=$2::jsonb,revision=revision+1,updated_at=now()
     WHERE owner_key=$1
   `,[this.owner(subject),JSON.stringify(this.seal(subject,next))]);
   await db.query('COMMIT');began=false;
   return {value:next};
  }catch(error){
   if(began)try{await db.query('ROLLBACK')}catch{}
   throw error;
  }finally{db.release()}
 }
 async disconnect(subject){
  // Retain a tombstone, so an in-flight worker cannot accidentally restore
  // the credential by inserting an obsolete refresh result.
  const result=await this.pool.query(`
    UPDATE qr_drive_owner_credentials SET
      disconnected=true,revision=revision+1,updated_at=now()
    WHERE owner_key=$1 AND disconnected=false
    RETURNING revision
  `,[this.owner(subject)]);
  return result.rowCount===1;
 }
}
