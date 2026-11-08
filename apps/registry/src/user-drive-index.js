import fs from 'node:fs';
import path from 'node:path';
import {createCipheriv, createDecipheriv, createHmac, randomBytes, createHash} from 'node:crypto';

// Encrypted, tenant-scoped Drive text preview. Separate from the legacy shared
// single-user Semantic Codex worker. No automatic admission into QualityRAG.
const MAX_DOCS=40;
const MAX_TOTAL=1_500_000;
const MAX_PER_FILE=96_000;
const SEARCH_LIMIT=30;
const MAX_QUERY=120;
const MAX_AGE_MS=60*60*1000;
const sha=data=>createHash('sha256').update(data).digest('hex');
const stop=(msg)=>{throw Error(msg)};
function check(condition,reason){if(!condition)stop(reason)}
function terms(text){
 return [...new Set((text.toLowerCase().match(/[\p{L}\p{N}][\p{L}\p{N}_-]*/gu)||[])
   .filter(x=>x.length>1).slice(0,12))];
}
function boundedName(value){
 return typeof value==='string'?value.slice(0,180):'';
}
export class UserDriveIndex {
 constructor({dir,encryptionKey,now=()=>Date.now()}){
  check(typeof dir==='string'&&dir.length>0,'DRIVE_INDEX_DIRECTORY_REQUIRED');
  const key=Buffer.from(encryptionKey||'','base64');
  check(key.length===32&&key.toString('base64')===encryptionKey,'INVALID_DRIVE_INDEX_KEY');
  this.dir=dir;this.key=key;this.now=now;
 }
 location(subject){
  check(typeof subject==='string'&&subject.length>0,'DRIVE_INDEX_SUBJECT_REQUIRED');
  const name=createHmac('sha256',this.key).update('qualityrag.index-owner/v1:'+subject)
    .digest('hex');
  return path.join(this.dir,name+'.json');
 }
 encode(subject,snapshot){
  const iv=randomBytes(12), cipher=createCipheriv('aes-256-gcm',this.key,iv);
  cipher.setAAD(Buffer.from('qualityrag.drive-index/v1:'+subject));
  const raw=Buffer.concat([cipher.update(JSON.stringify(snapshot),'utf8'),cipher.final()]);
  return {v:1,iv:iv.toString('base64url'),ct:raw.toString('base64url'),
    tag:cipher.getAuthTag().toString('base64url')};
 }
 load(subject){
  const location=this.location(subject);
  if(!fs.existsSync(location))return null;
  try{
   const st=fs.lstatSync(location);
   check(st.isFile()&&!st.isSymbolicLink()&&(st.mode&0o077)===0&&st.size<5_000_000,
    'DRIVE_INDEX_INTEGRITY_FAILURE');
   const envelope=JSON.parse(fs.readFileSync(location,'utf8'));
   check(envelope.v===1,'DRIVE_INDEX_INTEGRITY_FAILURE');
   const decipher=createDecipheriv('aes-256-gcm',this.key,Buffer.from(envelope.iv,'base64url'));
   decipher.setAAD(Buffer.from('qualityrag.drive-index/v1:'+subject));
   decipher.setAuthTag(Buffer.from(envelope.tag,'base64url'));
   const snapshot=JSON.parse(Buffer.concat([decipher.update(Buffer.from(envelope.ct,'base64url')),
     decipher.final()]).toString('utf8'));
   check(snapshot.schema==='qualityrag.user-drive-text-index/v1'&&
     Array.isArray(snapshot.entries),'DRIVE_INDEX_INTEGRITY_FAILURE');
   return snapshot;
  }catch{stop('DRIVE_INDEX_INTEGRITY_FAILURE')}
 }
 save(subject,snapshot){
  const destination=this.location(subject);
  fs.mkdirSync(this.dir,{recursive:true,mode:0o700});
  const tmp=destination+'.'+process.pid+'.'+randomBytes(7).toString('hex')+'.tmp';
  try{
   fs.writeFileSync(tmp,JSON.stringify(this.encode(subject,snapshot)),{mode:0o600,flag:'wx'});
   fs.renameSync(tmp,destination);
  }catch(e){try{fs.unlinkSync(tmp)}catch{};throw e}
 }
 clear(subject){
  const location=this.location(subject);
  try{fs.unlinkSync(location)}catch(e){if(e.code!=='ENOENT')throw e}
  return {indexed:false,removed:true};
 }
 bound(subject,connection){
  if(!connection?.connected||typeof connection.email!=='string'||
    typeof connection.folderId!=='string'||!connection.folderId)return null;
  const snapshot=this.load(subject);
  if(!snapshot)return null;
  if(snapshot.account!==connection.email||snapshot.folderId!==connection.folderId)return null;
  return snapshot;
 }
 status(subject,connection){
  const snap=this.bound(subject,connection);
  if(!snap)return {indexed:false,sourceCount:0,syncStatus:'NOT_INDEXED',coverage:'UNKNOWN'};
  const age=this.now()-Date.parse(snap.syncedAt);
  return {indexed:true,sourceCount:snap.entries.length,lastSyncedAt:snap.syncedAt,
    syncStatus:age>=MAX_AGE_MS?'STALE':'READY',
    coverage:snap.coverage,summary:snap.summary,
    sourceScope:'single selected Google Drive folder',semantics:'BOUNDED_LEXICAL_ONLY'};
 }
 async sync(subject,connector){
  const connection=connector.status(subject);
  check(connection.connected,'DRIVE_CONNECTION_NOT_FOUND');
  check(typeof connection.folderId==='string'&&connection.folderId!=='root',
    'DRIVE_SYNC_EXPLICIT_FOLDER_REQUIRED');
  const listing=await connector.selectedFiles(subject);
  // Do not advertise a complete snapshot based on a truncated folder listing.
  check(!listing.truncated&&listing.files.length<=100,'DRIVE_SYNC_FOLDER_TOO_LARGE');
  const supported=listing.files.filter(f=>connector.supportsText(f.mimeType));
  check(supported.length<=MAX_DOCS,'DRIVE_SYNC_TOO_MANY_TEXT_FILES');
  const entries=[];
  const summary={listed:listing.files.length,eligible:supported.length,
    unsupported:listing.files.length-supported.length,indexed:0,failed:0,
    excludedEmpty:0,tooLarge:0,truncatedLines:0};
  let total=0;
  for(const file of supported){
    try{
      const bytes=await connector.downloadSelectedText(subject,file.id,connection.folderId,
        MAX_PER_FILE);
      if(!bytes.length){summary.excludedEmpty++;continue}
      if(total+bytes.length>MAX_TOTAL)stop('DRIVE_INDEX_TOTAL_LIMIT');
      const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
      const lines=text.replace(/\r\n?/g,'\n').split('\n');
      // Keep the original line anchors and bound the maximum line length.
      if(lines.length>6000||lines.some(line=>line.length>1200))summary.truncatedLines++;
      entries.push({fileRef:sha('drive:'+file.id),fileId:file.id,
        name:boundedName(file.name),
        mimeType:file.mimeType,revision:sha(bytes),
        sourceId:'google_drive/'+sha(subject+':'+file.id).slice(0,32),
        lines:lines.slice(0,6000).map(line=>line.slice(0,1200))});
      total+=bytes.length;summary.indexed++;
    }catch(error){
      if(error?.message==='DRIVE_INDEX_TOTAL_LIMIT')throw error;
      if(error?.message==='DRIVE_SOURCE_TOO_LARGE')summary.tooLarge++;
      else summary.failed++;
    }
  }
  if(supported.length>0&&!entries.length&&summary.failed>0)
    stop('DRIVE_SYNC_ALL_DOCUMENTS_FAILED');
  const snapshot={schema:'qualityrag.user-drive-text-index/v1',
    account:connection.email,folderId:connection.folderId,
    syncedAt:new Date(this.now()).toISOString(),
    summary,coverage:summary.unsupported||summary.failed||summary.tooLarge||summary.excludedEmpty||summary.truncatedLines?
      'PARTIAL':'SELECTED_FOLDER_TEXT_FILES',entries};
  // Atomic replacement prunes removed/deleted sources on each successful resync.
  // Search rejects a changed account/folder even if an old index remains on disk.
  this.save(subject,snapshot);
  return this.status(subject,connection);
 }
 search(subject,connection,query){
  check(typeof query==='string'&&query.trim().length>1&&query.length<=MAX_QUERY,
    'INVALID_DRIVE_SEARCH_QUERY');
  const tokens=terms(query);
  check(tokens.length>0&&tokens.length<=12,'INVALID_DRIVE_SEARCH_QUERY');
  const snap=this.bound(subject,connection);
  if(!snap)return {hits:[],indexed:false,coverage:'UNKNOWN',reason:'NOT_INDEXED'};
  const age=this.now()-Date.parse(snap.syncedAt);
  if(!Number.isFinite(age)||age<0||age>MAX_AGE_MS)
    return {hits:[],indexed:true,coverage:'STALE',reason:'SYNC_REQUIRED',lastSyncedAt:snap.syncedAt};
  const hits=[];
  for(const source of snap.entries){
    for(let line=0;line<source.lines.length;line++){
      const original=source.lines[line],lower=original.toLowerCase();
      if(!tokens.every(term=>lower.includes(term)))continue;
      hits.push({source_id:source.sourceId,revision:source.revision,
        source_url:source.mimeType==='application/vnd.google-apps.document'?
          'https://docs.google.com/document/d/'+encodeURIComponent(source.fileId)+'/edit':
          'https://drive.google.com/file/d/'+encodeURIComponent(source.fileId)+'/view',
        file_name:source.name,mime_type:source.mimeType,
        anchor:{kind:'text_line',line_number:line+1},
        field:'extracted_text',matched_text:original.slice(0,350),
        matching_terms:tokens.length,quality:'LEXICAL_MATCH_NOT_EVIDENCE_ADMISSION'});
      if(hits.length>SEARCH_LIMIT)break;
    }
    if(hits.length>SEARCH_LIMIT)break;
  }
  return {hits:hits.slice(0,SEARCH_LIMIT),truncated:hits.length>SEARCH_LIMIT,
    indexed:true,coverage:snap.coverage,sourceCount:snap.entries.length,
    lastSyncedAt:snap.syncedAt,assurance:'NOT_EVALUATED_BY_PACKSPEC'};
 }
}
