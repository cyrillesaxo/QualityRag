// Explicit, single-process, loopback-only pilot composition.
// This is not a production deployment or multi-process durable transaction layer.
import fs from 'node:fs';
import path from 'node:path';
import {GoogleDriveConnections} from './google-drive-connections.js';
import {UserDriveIndex} from './user-drive-index.js';
import {EvidenceLedger} from './evidence-ledger.js';
import {loadProtectedReviewTrust} from './protected-admission.js';
import {parseProtectedDriveServices} from './protected-drive.js';

const required=(env,key)=>{
 const value=env[key];
 if(typeof value!=='string'||!value.trim())
  throw Error('PILOT_REQUIRED_'+key);
 return value;
};
const key=(value)=>{
 const bytes=Buffer.from(value,'base64');
 if(bytes.length!==32||bytes.toString('base64')!==value)
  throw Error('PILOT_INVALID_ENCRYPTION_KEY');
 return value;
};
function privateDirectory(value){
 if(!path.isAbsolute(value))throw Error('PILOT_ABSOLUTE_DIRECTORY_REQUIRED');
 const resolved=path.resolve(value);
 if(resolved==='/'||resolved===path.parse(resolved).root)
  throw Error('PILOT_UNSAFE_DIRECTORY');
 const s=fs.lstatSync(resolved);
 if(!s.isDirectory()||s.isSymbolicLink()||(s.mode&0o077)!==0)
  throw Error('PILOT_DIRECTORY_NOT_PRIVATE');
 return resolved;
}
function validateChild(root,target){
 const full=path.resolve(root,target);
 if(!full.startsWith(root+path.sep))throw Error('PILOT_STORAGE_OUTSIDE_PRIVATE_DIRECTORY');
 if(fs.existsSync(full)){
  const s=fs.lstatSync(full);
  if(!s.isFile()||s.isSymbolicLink()||(s.mode&0o077)!==0)
   throw Error('PILOT_STORAGE_NOT_PRIVATE');
 }
 return full;
}
export function createPilotComponents(env,{fetchImpl,cursorCoordinator=null,oauthPending=null,credentialStore=null}={}){
 if(env.QUALITYRAG_PILOT_MODE!=='true')return {
  driveManager:null,driveIndex:null,evidenceLedger:null,
  protectedReviewTrust:null,protectedDriveServices:new Set()
 };
 if(env.QUALITYRAG_AUTH_MODE!=='oidc')
  throw Error('PILOT_REQUIRES_OIDC');
 if(!['127.0.0.1','::1','localhost'].includes(env.QUALITYRAG_BIND_HOST))
  throw Error('PILOT_REQUIRES_LOOPBACK_BIND');
 if(env.QUALITYRAG_PILOT_APPROVED_NETWORK!=='true')
  throw Error('PILOT_NETWORK_APPROVAL_REQUIRED');
 const root=privateDirectory(required(env,'QUALITYRAG_PILOT_DATA_DIR'));
 const driveKey=key(required(env,'QUALITYRAG_DRIVE_ENCRYPTION_KEY'));
 const indexKey=key(required(env,'QUALITYRAG_DRIVE_INDEX_KEY'));
 if(driveKey===indexKey)throw Error('PILOT_KEY_SEPARATION_REQUIRED');
 const scopes=parseProtectedDriveServices(required(env,'QUALITYRAG_PROTECTED_DRIVE_SERVICES'));
 if(scopes.size===0)throw Error('PILOT_PROTECTED_SERVICE_REQUIRED');
 const trustFile=required(env,'QUALITYRAG_PROTECTED_REVIEW_KEYS_FILE');
 if(!path.isAbsolute(trustFile))throw Error('PILOT_TRUST_PATH_NOT_ABSOLUTE');
 const trustStat=fs.lstatSync(trustFile);
 if(!trustStat.isFile()||trustStat.isSymbolicLink()||
    (trustStat.mode&0o077)!==0)
  throw Error('PILOT_TRUST_FILE_NOT_PRIVATE');
 const protectedReviewTrust=loadProtectedReviewTrust(trustFile);
 const files={
  credentials:validateChild(root,'google-credentials.json'),
  ledger:validateChild(root,'evidence-ledger.jsonl'),
  index:path.join(root,'drive-index')
 };
 if(fs.existsSync(files.index)){
  const s=fs.lstatSync(files.index);
  if(!s.isDirectory()||s.isSymbolicLink()||(s.mode&0o077)!==0)
   throw Error('PILOT_DIRECTORY_NOT_PRIVATE');
 }
 // US-068: shared state is all-or-nothing. Coordinated cursors without shared OAuth state and shared
 // credentials would let one replica connect while another still reads its own local file.
 if((cursorCoordinator||oauthPending||credentialStore)&&!(cursorCoordinator&&oauthPending&&credentialStore))
  throw Error('PILOT_SHARED_DRIVE_STATE_INCOMPLETE');
 const driveManager=new GoogleDriveConnections({
  file:files.credentials,encryptionKey:driveKey,
  clientId:required(env,'QUALITYRAG_GOOGLE_CLIENT_ID'),
  clientSecret:required(env,'QUALITYRAG_GOOGLE_CLIENT_SECRET'),
  redirectUri:required(env,'QUALITYRAG_GOOGLE_REDIRECT_URI'),
  studioOrigin:required(env,'QUALITYRAG_STUDIO_ORIGIN'),
  oauthPending,credentialStore,
  ...(fetchImpl?{fetchImpl}:{})
 });
 const driveIndex=new UserDriveIndex({dir:files.index,encryptionKey:indexKey,
  cursorCoordinator});
 const evidenceLedger=new EvidenceLedger(files.ledger);
 return {driveManager,driveIndex,evidenceLedger,protectedReviewTrust,
  protectedDriveServices:scopes};
}
