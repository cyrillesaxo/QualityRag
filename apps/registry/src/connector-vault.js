import {randomBytes,createCipheriv,createDecipheriv,createHash} from 'node:crypto';

// Encryption primitive for the server-side connector vault. Persist the resulting
// record in a tenant-scoped database, not in the Studio browser or repository.
const KEY_BYTES=32;
export function connectorKeyFromBase64(value){
 if(typeof value!=='string'||!value)throw new Error('CONNECTOR_KEY_REQUIRED');
 const key=Buffer.from(value,'base64');
 if(key.length!==KEY_BYTES||key.toString('base64')!==value)throw new Error('INVALID_CONNECTOR_KEY');
 return key;
}
function context(tenantId,principalId,provider,connectionId){
 for(const [name,v] of Object.entries({tenantId,principalId,provider,connectionId})){
  if(typeof v!=='string'||!v||v.length>256)throw new Error('INVALID_'+name.toUpperCase());
 }
 return JSON.stringify([tenantId,principalId,provider,connectionId]);
}
export function sealConnectorCredential(key,{tenantId,principalId,provider,connectionId,credential}){
 if(!Buffer.isBuffer(key)||key.length!==KEY_BYTES)throw new Error('INVALID_CONNECTOR_KEY');
 if(!credential||typeof credential.refresh_token!=='string'||!credential.refresh_token)throw new Error('REFRESH_TOKEN_REQUIRED');
 const aad=context(tenantId,principalId,provider,connectionId);
 const nonce=randomBytes(12),cipher=createCipheriv('aes-256-gcm',key,nonce);
 cipher.setAAD(Buffer.from(aad));
 const plaintext=Buffer.from(JSON.stringify(credential),'utf8');
 const ciphertext=Buffer.concat([cipher.update(plaintext),cipher.final()]);
 return {version:1,algorithm:'AES-256-GCM',nonce:nonce.toString('base64'),tag:cipher.getAuthTag().toString('base64'),
  ciphertext:ciphertext.toString('base64'),context_hash:createHash('sha256').update(aad).digest('hex')};
}
export function openConnectorCredential(key,{tenantId,principalId,provider,connectionId,record}){
 if(!Buffer.isBuffer(key)||key.length!==KEY_BYTES)throw new Error('INVALID_CONNECTOR_KEY');
 const aad=context(tenantId,principalId,provider,connectionId);
 if(!record||record.version!==1||record.algorithm!=='AES-256-GCM'||
   record.context_hash!==createHash('sha256').update(aad).digest('hex'))throw new Error('CONNECTOR_CONTEXT_MISMATCH');
 try{
  const nonce=Buffer.from(record.nonce,'base64'),tag=Buffer.from(record.tag,'base64');
  if(nonce.length!==12||tag.length!==16)throw new Error('INVALID_CIPHERTEXT');
  const decipher=createDecipheriv('aes-256-gcm',key,nonce);decipher.setAAD(Buffer.from(aad));decipher.setAuthTag(tag);
  const plaintext=Buffer.concat([decipher.update(Buffer.from(record.ciphertext,'base64')),decipher.final()]);
  return JSON.parse(plaintext.toString('utf8'));
 }catch{throw new Error('CONNECTOR_CREDENTIAL_DECRYPT_FAILED')}
}
