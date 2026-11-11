import fs from 'node:fs';
import path from 'node:path';
import {createCipheriv, createDecipheriv, createHmac, randomBytes, createHash} from 'node:crypto';
import {scanReviewedSourceConstraints} from './constraint-sufficiency.js';
import {scanRelationshipConflicts} from './cross-document-relations.js';

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
 constructor({dir,encryptionKey,now=()=>Date.now(),cursorCoordinator=null}){
  check(typeof dir==='string'&&dir.length>0,'DRIVE_INDEX_DIRECTORY_REQUIRED');
  const key=Buffer.from(encryptionKey||'','base64');
  check(key.length===32&&key.toString('base64')===encryptionKey,'INVALID_DRIVE_INDEX_KEY');
  this.dir=dir;this.key=key;this.now=now;
  this.activeSyncs=new Set();this.generations=new Map();
  this.cursorCoordinator=cursorCoordinator;
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
 decode(subject,envelope){
  check(envelope?.v===1,'DRIVE_INDEX_INTEGRITY_FAILURE');
  const decipher=createDecipheriv('aes-256-gcm',this.key,
    Buffer.from(envelope.iv,'base64url'));
  decipher.setAAD(Buffer.from('qualityrag.drive-index/v1:'+subject));
  decipher.setAuthTag(Buffer.from(envelope.tag,'base64url'));
  return JSON.parse(Buffer.concat([
    decipher.update(Buffer.from(envelope.ct,'base64url')),
    decipher.final()
  ]).toString('utf8'));
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
  // Fence any in-progress network synchronization before erasing the file.
  this.generations.set(location,(this.generations.get(location)||0)+1);
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
    sourceControls:{
      searchable:snap.entries.filter(e=>e.searchEnabled!==false).length,
      excluded:snap.entries.filter(e=>e.searchEnabled===false).length,
      reviewedForGovernance:0
    },
    sourceScope:'single selected Google Drive folder',semantics:'BOUNDED_LEXICAL_ONLY',
    sourceTruth:'UNVERIFIED',packSpecAdmission:'NOT_PERFORMED',
    activityLogScope:'LOCAL_UNATTESTED'};
 }
 async sync(subject,connector){
  const ownerKey=this.location(subject);
  check(!this.activeSyncs.has(ownerKey),'DRIVE_SYNC_IN_PROGRESS');
  this.activeSyncs.add(ownerKey);
  const startGeneration=this.generations.get(ownerKey)||0;
  try{
  const connection=connector.status(subject);
  check(connection.connected,'DRIVE_CONNECTION_NOT_FOUND');
  // Capture before reading listing and bytes: changes during indexing can
  // later be discovered from this durable cursor, not silently missed.
  let changePageToken=null;
  try{
    if(typeof connector.driveChangeStartToken==='function')
      changePageToken=await connector.driveChangeStartToken(subject);
  }catch{/* Cursor unavailable => poll status UNKNOWN, not approved. */}
  check(typeof connection.folderId==='string'&&connection.folderId!=='root',
    'DRIVE_SYNC_EXPLICIT_FOLDER_REQUIRED');
  const listing=await connector.selectedFiles(subject);
  // Do not advertise a complete snapshot based on a truncated folder listing.
  check(!listing.truncated&&listing.files.length<=100,'DRIVE_SYNC_FOLDER_TOO_LARGE');
  const supported=listing.files.filter(f=>connector.supportsText(f.mimeType));
  check(supported.length<=MAX_DOCS,'DRIVE_SYNC_TOO_MANY_TEXT_FILES');
  const entries=[];
  // Preserve owner exclusions across source revisions and successful resyncs,
  // but only for this same authenticated account and selected folder.
  const prior=this.bound(subject,connection);
  const oldControls=new Map((prior?.entries||[]).map(e=>[e.fileId,e.searchEnabled!==false]));
  const inventory=listing.files.map(f=>({
    name:boundedName(f.name),mimeType:f.mimeType,
    status:connector.supportsText(f.mimeType)?'PENDING':'UNSUPPORTED'
  }));
  const summary={listed:listing.files.length,eligible:supported.length,
    unsupported:listing.files.length-supported.length,indexed:0,failed:0,
    excludedEmpty:0,tooLarge:0,truncatedLines:0};
  let total=0;
  for(const file of supported){
    const auditRow=inventory.find(x=>x.name===boundedName(file.name)&&
      x.mimeType===file.mimeType&&x.status==='PENDING');
    try{
      const bytes=await connector.downloadSelectedText(subject,file.id,connection.folderId,
        MAX_PER_FILE);
      if(!bytes.length){summary.excludedEmpty++;if(auditRow)auditRow.status='EMPTY';continue}
      if(total+bytes.length>MAX_TOTAL)stop('DRIVE_INDEX_TOTAL_LIMIT');
      const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
      const lines=text.replace(/\r\n?/g,'\n').split('\n');
      // Keep the original line anchors and bound the maximum line length.
      if(lines.length>6000||lines.some(line=>line.length>1200))summary.truncatedLines++;
      entries.push({fileRef:sha('drive:'+file.id),fileId:file.id,
        name:boundedName(file.name),
        mimeType:file.mimeType,revision:sha(bytes),
        sourceId:'google_drive/'+createHmac('sha256',this.key)
          .update('qualityrag.source/v1:'+subject+':'+file.id).digest('hex').slice(0,32),
        searchEnabled:oldControls.get(file.id)??true,
        lines:lines.slice(0,6000).map(line=>line.slice(0,1200))});
      if(auditRow){auditRow.status=lines.length>6000||lines.some(line=>line.length>1200)?
        'TRUNCATED':'INDEXED';}
      total+=bytes.length;summary.indexed++;
    }catch(error){
      if(error?.message==='DRIVE_INDEX_TOTAL_LIMIT')throw error;
      if(error?.message==='DRIVE_SOURCE_TOO_LARGE'){
        summary.tooLarge++;if(auditRow)auditRow.status='TOO_LARGE';
      }else{
        summary.failed++;if(auditRow)auditRow.status='FAILED';
      }
    }
  }
  // An empty/failed scan replaces the previous snapshot; never keep revoked
  // content just because all eligible files could not be downloaded.
  const snapshot={schema:'qualityrag.user-drive-text-index/v1',
    account:connection.email,folderId:connection.folderId,
    syncedAt:new Date(this.now()).toISOString(),
    changePageToken,baselineId:randomBytes(16).toString('hex'),
    summary,inventory,
    controlHistory:(prior?.controlHistory||[]).slice(-100),
    coverage:summary.unsupported||summary.failed||summary.tooLarge||summary.excludedEmpty||summary.truncatedLines?
      'PARTIAL':'SELECTED_FOLDER_TEXT_FILES',entries};
  // Atomic replacement prunes removed/deleted sources on each successful resync.
  // Search rejects a changed account/folder even if an old index remains on disk.
  const latest=connector.status(subject);
  check((this.generations.get(ownerKey)||0)===startGeneration,
    'DRIVE_SYNC_INVALIDATED');
  check(latest.connected&&latest.email===connection.email&&
    latest.folderId===connection.folderId,'DRIVE_SYNC_INVALIDATED');
  // The file index is a local baseline; the PG checkpoint is a separate
  // authority. A crash between these writes leaves UNKNOWN, never SAT.
  // Multi-replica shared baseline coordination is NOT established by this.
  this.save(subject,snapshot);
  if(this.cursorCoordinator){
    check(typeof changePageToken==='string','DRIVE_CURSOR_NOT_AVAILABLE');
    await this.cursorCoordinator.establish(subject,snapshot,
      this.encode(subject,{cursor:changePageToken}));
  }
  return this.status(subject,connection);
  }catch(error){
    if(error?.message==='DRIVE_AUTHORIZATION_REQUIRED')this.clear(subject);
    throw error;
  }finally{
    this.activeSyncs.delete(ownerKey);
  }
 }
 visibility(subject,connection){
  const snap=this.bound(subject,connection);
  if(!snap)return {indexed:false,coverage:'UNKNOWN',sources:[],inventory:[],
    activity:[],sourceTruth:'UNVERIFIED',packSpecAdmission:'NOT_PERFORMED'};
  const age=this.now()-Date.parse(snap.syncedAt);
  return {
    indexed:true,lastSyncedAt:snap.syncedAt,
    stale:!Number.isFinite(age)||age<0||age>MAX_AGE_MS,
    account:connection.email,folderId:connection.folderId,
    scope:'ONE_SELECTED_FOLDER_DIRECT_CHILDREN',
    coverage:snap.coverage,summary:snap.summary,
    sourceTruth:'UNVERIFIED',packSpecAdmission:'NOT_PERFORMED',
    activityLogScope:'LOCAL_UNATTESTED',
    sources:snap.entries.map(e=>({
      sourceId:e.sourceId,filename:e.name,mimeType:e.mimeType,
      revision:e.revision,lineCount:e.lines.length,
      searchable:e.searchEnabled!==false,
      evidenceStatus:'NOT_REVIEWED',
      provenanceStatus:'CALLER_DECLARED_NOT_VERIFIED'
    })),
    inventory:snap.inventory||[],
    activity:(snap.controlHistory||[]).slice(-30).reverse()
  };
 }
 controlSource(subject,connection,input){
  check(input&&!Array.isArray(input)&&typeof input==='object'&&
    Object.keys(input).length===3&&Object.hasOwn(input,'sourceId')&&
    Object.hasOwn(input,'searchable')&&Object.hasOwn(input,'reason'),
    'INVALID_DRIVE_SOURCE_CONTROL');
  check(typeof input.sourceId==='string'&&
    /^google_drive[/][a-f0-9]{32}$/.test(input.sourceId)&&
    typeof input.searchable==='boolean'&&
    (input.searchable?input.reason==='OWNER_SELECTION':
      ['SENSITIVE','OUT_OF_SCOPE','NEEDS_REVIEW'].includes(input.reason)),
    'INVALID_DRIVE_SOURCE_CONTROL');
  const location=this.location(subject);
  check(!this.activeSyncs.has(location),'DRIVE_SYNC_IN_PROGRESS');
  const snap=this.bound(subject,connection);
  check(snap,'DRIVE_INDEX_NOT_FOUND');
  const item=snap.entries.find(e=>e.sourceId===input.sourceId);
  check(item,'DRIVE_SOURCE_NOT_FOUND');
  const before=item.searchEnabled!==false;
  if(before===input.searchable)return {changed:false,visibility:this.visibility(subject,connection)};
  item.searchEnabled=input.searchable;
  snap.controlHistory=[...(snap.controlHistory||[]),{
    at:new Date(this.now()).toISOString(),
    sourceId:item.sourceId,action:input.searchable?'INCLUDE':'EXCLUDE',
    reason:input.reason
  }].slice(-100);
  this.save(subject,snap);
  return {changed:true,visibility:this.visibility(subject,connection)};
 }
 /**
  * Bounded owner-folder drift poll against the encrypted last-synced index.
  * Read-only: this never overwrites the baseline, never admits evidence,
  * and never returns filenames, file IDs or provider response bodies.
  * The operator/owner must request a new authorized sync after CHANGED.
  */
 /**
  * Fail-closed Google Drive Changes cursor poll. A token is captured before
  * indexing, stored inside the existing AES-GCM per-owner snapshot, and
  * advanced only after all bounded pages have been verified. No cursor,
  * ambiguous event, 410, truncation, or provider failure permits a MATCHED
  * verdict. Cursor state is never exposed to the browser or API.
  */
 async inspectDriveChangeCursor(subject,connector,snapshot,connection){
  const unknown={state:'UNKNOWN',completed:false};
  if(typeof connector.driveChangePage!=='function')return unknown;
  const coordinator=this.cursorCoordinator;
  let cursor,checkpoint=null,generation=null,binding=null;
  try{
   if(coordinator){
     checkpoint=await coordinator.read(subject);
     generation=coordinator.generation(subject,snapshot);
     binding=coordinator.binding(subject,connection);
     if(!checkpoint||checkpoint.stale||
        checkpoint.generation!==generation||checkpoint.binding_digest!==binding)
       return unknown;
     const decoded=this.decode(subject,checkpoint.encrypted_cursor);
     cursor=decoded.cursor;
   }else cursor=snapshot?.changePageToken;
   if(typeof cursor!=='string'||!cursor.length)return unknown;
   const known=new Set(snapshot.entries.map(x=>x.fileId));
   let final=null;
   const seen=new Set();
   for(let pageIndex=0;pageIndex<5;pageIndex++){
     if(seen.has(cursor))return unknown;
     seen.add(cursor);
     const page=await connector.driveChangePage(subject,cursor);
     if(!page||!Array.isArray(page.changes)||page.changes.length>100)return unknown;
     for(const item of page.changes){
       if(!item||typeof item.fileId!=='string')return unknown;
       if(known.has(item.fileId)||item.fileId===connection.folderId||
          item.parents?.includes(connection.folderId)){
         if(coordinator){
           const status=await coordinator.markStale({subject,generation,binding});
           return status==='STALE'?{state:'CHANGED',completed:true}:unknown;
         }
         return {state:'CHANGED',completed:true};
       }
       if(item.removed||!item.metadataAvailable)return unknown;
     }
     if(typeof page.newStartPageToken==='string'&&!page.nextPageToken){
       final=page.newStartPageToken;break;
     }
     if(typeof page.nextPageToken!=='string')return unknown;
     cursor=page.nextPageToken;
   }
   if(!final)return unknown;
   const after=connector.status(subject),existing=this.bound(subject,after);
   if(!after.connected||after.email!==connection.email||
     after.folderId!==connection.folderId||
     existing?.syncedAt!==snapshot.syncedAt||
     this.activeSyncs.has(this.location(subject)))return unknown;
   if(coordinator){
     // The current process's file and shared checkpoint must still describe
     // the same baseline. The SQL conditional update fences a competing poll.
     if(coordinator.generation(subject,existing)!==generation)return unknown;
     const version=Number(checkpoint.cursor_version);
     if(!Number.isSafeInteger(version))return unknown;
     const result=await coordinator.advance({
       subject,generation,binding,version,
       encryptedCursor:this.encode(subject,{cursor:final})
     });
     if(result!=='ADVANCED')return unknown;
     // Confirm that a concurrent local sync or control edit did not supersede
     // the baseline during the database round trip.
     const latest=connector.status(subject);
     const latestSnapshot=this.bound(subject,latest);
     if(!latestSnapshot||
       coordinator.generation(subject,latestSnapshot)!==generation||
       latest.folderId!==connection.folderId||latest.email!==connection.email)
       return unknown;
   }else{
     if(existing?.changePageToken!==snapshot.changePageToken)return unknown;
     if(final!==snapshot.changePageToken)
       this.save(subject,{...snapshot,changePageToken:final});
   }
   return {state:'NO_RELEVANT_EVENTS',completed:true};
  }catch{return unknown}
 }
 async inspectSelectedFolderDrift(subject,connector){
  const unchanged={schema:'qualityrag.drive-folder-drift/v1',
    state:'UNKNOWN',checkedAt:null,sourceBytesVerified:false,
    selectionCompletenessVerified:false,releasePermitted:false};
  if(this.activeSyncs.has(this.location(subject)))return unchanged;
  let conn,before;
  try{
   conn=connector.status(subject);
   before=this.bound(subject,conn);
   if(!conn?.connected||!before||!conn.folderId||conn.folderId==='root'||
      before.coverage!=='SELECTED_FOLDER_TEXT_FILES'||!Array.isArray(before.entries))
     return unchanged;
   const age=this.now()-Date.parse(before.syncedAt);
   if(!Number.isFinite(age)||age<0||age>MAX_AGE_MS)return unchanged;
   const inventory=await connector.selectedFiles(subject);
   if(inventory.truncated||inventory.folderId!==conn.folderId||
      !Array.isArray(inventory.files)||inventory.files.length>100)return unchanged;
   const indexed=before.entries;
   const eligible=inventory.files.filter(file=>connector.supportsText(file.mimeType));
   // A newly unsupported file also changes governance coverage. Never
   // claim complete folder equality based on the text-only subset.
   if(eligible.length!==inventory.files.length)
     return {...unchanged,state:'CHANGED'};
   if(eligible.length>MAX_DOCS||indexed.length!==eligible.length||
      indexed.length>MAX_DOCS)
     return {...unchanged,state:'CHANGED'};
   const expected=new Map(indexed.map(x=>[x.fileId,x]));
   if(expected.size!==indexed.length)return unchanged;
   const current=new Map(eligible.map(x=>[x.id,x]));
   if(current.size!==eligible.length)return unchanged;
   if([...expected].some(([id,entry])=>!current.has(id)||
      current.get(id).mimeType!==entry.mimeType))
     return {...unchanged,state:'CHANGED'};
   // Whole-folder included-source check: newly inserted text, deletion,
   // owner exclusion and any byte changes conservatively invalidate.
   const generation=this.generations.get(this.location(subject))||0;
   for(const [fileId,source] of expected){
     if(source.searchEnabled===false)return {...unchanged,state:'CHANGED'};
     const bytes=await connector.downloadSelectedText(
       subject,fileId,conn.folderId,MAX_PER_FILE);
     if(!Buffer.isBuffer(bytes)||sha(bytes)!==source.revision)
       return {...unchanged,state:'CHANGED'};
   }
   const after=connector.status(subject);
   if(!after?.connected||after.folderId!==conn.folderId||
      after.email!==conn.email||
      (this.generations.get(this.location(subject))||0)!==generation||
      this.activeSyncs.has(this.location(subject)))
     return unchanged;
   // Full folder equality alone cannot establish no lost changes between
   // sync and this check; the cursor must complete and be advanced.
   const changeStatus=await this.inspectDriveChangeCursor(subject,connector,before,conn);
   if(changeStatus.state==='CHANGED')return {...unchanged,state:'CHANGED'};
   if(changeStatus.state!=='NO_RELEVANT_EVENTS')return unchanged;
   const now=new Date(this.now()).toISOString();
   return {...unchanged,state:'MATCHED_AT_CHECK_TIME',checkedAt:now,
     sourceBytesVerified:true,selectionCompletenessVerified:true};
  }catch{
   // Google 403, provider outage, lost index: no proof of permission.
   return unchanged;
  }
 }
 async verifyLiveApprovedWitnesses(subject,connector,witnesses,
   {includeWitnessLines=false,includeConstraintScan=false,
     includeRelationshipScan=false}={}){
  // Last-mile mandatory check: no signed claim alone bypasses current owner's
  // source controls. Re-fetch the exact file bytes from Google, including
  // the provider's parent-folder check, then re-check controls after all awaits.
  check(Array.isArray(witnesses)&&witnesses.length>0&&witnesses.length<=8,
    'PROTECTED_WITNESS_LIMIT');
  const ownerKey=this.location(subject);
  check(!this.activeSyncs.has(ownerKey),'PROTECTED_SOURCE_SYNC_IN_PROGRESS');
  const connection=connector.status(subject);
  const snapshot=this.bound(subject,connection);
  check(snapshot&&connection.folderId!=='root'&&
    snapshot.coverage==='SELECTED_FOLDER_TEXT_FILES',
    'PROTECTED_SOURCE_COVERAGE_INCOMPLETE');
  const age=this.now()-Date.parse(snapshot.syncedAt);
  check(Number.isFinite(age)&&age>=0&&age<=MAX_AGE_MS,
    'PROTECTED_SOURCE_INDEX_STALE');
  const expected=new Map();
  for(const witness of witnesses){
    const source=snapshot.entries.find(e=>e.sourceId===witness.sourceId);
    check(source,'PROTECTED_SOURCE_NOT_FOUND');
    check(source.searchEnabled!==false,'PROTECTED_OWNER_EXCLUDED_SOURCE');
    check(source.revision===witness.revision,'PROTECTED_SOURCE_REVISION_CHANGED');
    check(witness.lineNumber<=source.lines.length,
      'PROTECTED_SOURCE_ANCHOR_MISSING');
    check(sha(Buffer.from(source.lines[witness.lineNumber-1],'utf8'))===
      witness.lineSha256,'PROTECTED_SOURCE_LINE_CHANGED');
    expected.set(source.fileId,source);
  }
  const reviewedSourceCount=expected.size;
  const selectedIncluded=includeRelationshipScan?
    snapshot.entries.filter(e=>e.searchEnabled!==false):[];
  if(includeRelationshipScan){
    check(selectedIncluded.length>0&&selectedIncluded.length<=MAX_DOCS,
      'PROTECTED_RELATION_SELECTED_SCOPE_INCOMPLETE');
    for(const source of selectedIncluded){
      check(source&&typeof source.fileId==='string'&&
        Array.isArray(source.lines)&&source.lines.length>0&&
        source.lines.length<=6000&&
        source.lines.every(line=>typeof line==='string'&&line.length<=1200),
        'PROTECTED_RELATION_SELECTED_SCOPE_INCOMPLETE');
      expected.set(source.fileId,source);
    }
    // Protect against a malformed index with aliasing file IDs or source IDs.
    check(expected.size===selectedIncluded.length,
      'PROTECTED_RELATION_SELECTED_SCOPE_INCOMPLETE');
  }
  for(const [fileId,source] of expected){
    let bytes;
    try{
      bytes=await connector.downloadSelectedText(subject,fileId,
        connection.folderId,MAX_PER_FILE);
    }catch(error){
      if(error?.message==='DRIVE_AUTHORIZATION_REQUIRED')this.clear(subject);
      throw Error('PROTECTED_LIVE_GOOGLE_VERIFICATION_FAILED');
    }
    check(Buffer.isBuffer(bytes)&&sha(bytes)===source.revision,
      'PROTECTED_LIVE_SOURCE_REVISION_MISMATCH');
    let decoded;
    try{decoded=new TextDecoder('utf-8',{fatal:true}).decode(bytes)}
    catch{throw Error('PROTECTED_LIVE_SOURCE_INVALID_TEXT')}
    const lines=decoded.replace(/\r\n?/g,'\n').split('\n');
    check(lines.length===source.lines.length&&
      lines.every((line,i)=>line===source.lines[i]),
      'PROTECTED_LIVE_EXTRACTED_TEXT_MISMATCH');
  }
  // The only write after this function must be a synchronous ledger append,
  // so a concurrent owner exclusion cannot interleave between final check
  // and admission on this single-process research registry.
  check(!this.activeSyncs.has(ownerKey),'PROTECTED_SOURCE_SYNC_IN_PROGRESS');
  const latest=connector.status(subject),current=this.bound(subject,latest);
  check(latest.connected&&latest.email===connection.email&&
    latest.folderId===connection.folderId&&current&&
    current.syncedAt===snapshot.syncedAt&&
    current.coverage==='SELECTED_FOLDER_TEXT_FILES',
    'PROTECTED_OWNER_CONTEXT_CHANGED');
  for(const witness of witnesses){
    const source=current.entries.find(e=>e.sourceId===witness.sourceId);
    check(source&&source.searchEnabled!==false&&
      source.revision===witness.revision&&
      sha(Buffer.from(source.lines[witness.lineNumber-1]||'','utf8'))===
        witness.lineSha256,'PROTECTED_OWNER_CONTEXT_CHANGED');
  }
  if(includeRelationshipScan){
    // Check all included files, not only signed witness files, after the
    // provider reads. Exclusion during I/O invalidates the scan.
    const selectedNow=current.entries.filter(e=>e.searchEnabled!==false);
    check(selectedNow.length===selectedIncluded.length,
      'PROTECTED_RELATION_OWNER_SCOPE_CHANGED');
    for(const source of selectedIncluded){
      const latestSource=selectedNow.find(e=>e.fileId===source.fileId);
      check(latestSource&&latestSource.sourceId===source.sourceId&&
        latestSource.revision===source.revision&&
        latestSource.lines.length===source.lines.length,
        'PROTECTED_RELATION_OWNER_SCOPE_CHANGED');
    }
  }
  const verifiedLines=includeWitnessLines?witnesses.map(w=>{
    const source=current.entries.find(e=>e.sourceId===w.sourceId);
    const i=w.lineNumber-1;
    const context=[];
    if(i>0)context.push({lineNumber:i,text:source.lines[i-1]});
    if(i+1<source.lines.length)
      context.push({lineNumber:i+2,text:source.lines[i+1]});
    return {sourceId:w.sourceId,requirementId:w.requirementId,
      lineNumber:w.lineNumber,lineSha256:w.lineSha256,
      text:source.lines[i],context};
  }):undefined;
  // Exact live-byte verification already succeeded for each listed file.
  // Scan its entire indexed text (not just adjacent witness lines) for
  // lexical indicators requiring a new human review. The scan never
  // provides source authenticity or document-wide semantic completeness.
  const constraintScan=includeConstraintScan?scanReviewedSourceConstraints({
    sources:[...expected.values()].map(e=>({sourceId:e.sourceId,lines:e.lines})),
    witnesses
  }):undefined;
  const relationshipScan=includeRelationshipScan?
    scanRelationshipConflicts({
      sources:selectedIncluded.map(e=>({sourceId:e.sourceId,lines:e.lines})),
      witnesses
    }):undefined;
  return {owner:subject,folderId:connection.folderId,
    checkedAt:new Date(this.now()).toISOString(),
    sourceCount:reviewedSourceCount,
    verifiedExactLiveBytes:true,independentPublisherVerified:false,
    ...(includeWitnessLines?{verifiedLines}:{}),
    ...(includeConstraintScan?{constraintScan}:{}),
    ...(includeRelationshipScan?{relationshipScan}:{})};
 }
 checkGovernedCandidates(subject,connection,policy,policySha256,candidates){
  // Guarded route from Drive *candidates* to governed evaluation. It deliberately
  // cannot ADMIT because lexical text and owner consent do not attest semantics
  // or independent source provenance.
  check(policy&&typeof policy.id==='string'&&
    typeof policy.version==='string'&&Array.isArray(policy.requirements)&&
    typeof policySha256==='string'&&/^[0-9a-f]{64}$/.test(policySha256),
    'INVALID_DRIVE_GATE_POLICY');
  check(Array.isArray(candidates)&&candidates.length>=1&&candidates.length<=25,
    'INVALID_DRIVE_GATE_CANDIDATES');
  const reqs=new Set(policy.requirements.map(r=>r.id));
  const seen=new Set();
  for(const candidate of candidates){
    check(candidate&&typeof candidate==='object'&&!Array.isArray(candidate)&&
      Object.keys(candidate).length===4&&
      ['sourceId','revision','requirementId','lineNumber'].every(k=>
        Object.hasOwn(candidate,k))&&
      typeof candidate.sourceId==='string'&&
      /^google_drive[/][a-f0-9]{32}$/.test(candidate.sourceId)&&
      typeof candidate.revision==='string'&&/^[a-f0-9]{64}$/.test(candidate.revision)&&
      typeof candidate.requirementId==='string'&&
      reqs.has(candidate.requirementId)&&
      Number.isSafeInteger(candidate.lineNumber)&&
      candidate.lineNumber>=1&&candidate.lineNumber<=6000,
      'INVALID_DRIVE_GATE_CANDIDATE');
    const key=candidate.sourceId+':'+candidate.revision+':'+
      candidate.requirementId+':'+candidate.lineNumber;
    check(!seen.has(key),'DRIVE_GATE_DUPLICATE_CANDIDATE');
    seen.add(key);
  }
  const snapshot=this.bound(subject,connection);
  const age=snapshot?this.now()-Date.parse(snapshot.syncedAt):NaN;
  const fresh=Number.isFinite(age)&&age>=0&&age<=MAX_AGE_MS;
  const observations=candidates.map(candidate=>{
    const source=snapshot?.entries.find(e=>e.sourceId===candidate.sourceId);
    const reasons=[];
    if(!snapshot)reasons.push('NO_CURRENT_INDEX');
    else if(!source)reasons.push('SOURCE_NOT_IN_SELECTED_INDEX');
    // An explicit owner denial takes precedence over freshness and any
    // client-provided revision. Never let a stale cache conceal a denial.
    else if(source.searchEnabled===false)reasons.push('SOURCE_EXCLUDED_BY_OWNER');
    else if(!fresh)reasons.push('INDEX_STALE');
    else if(source.revision!==candidate.revision)reasons.push('SOURCE_REVISION_MISMATCH');
    else if(candidate.lineNumber>source.lines.length)reasons.push('ANCHOR_NOT_IN_EXTRACTED_TEXT');
    else reasons.push('SEMANTIC_SUPPORT_NOT_VERIFIED','SOURCE_PROVENANCE_NOT_VERIFIED');
    return {
      sourceId:candidate.sourceId,revision:candidate.revision,
      requirementId:candidate.requirementId,lineNumber:candidate.lineNumber,
      eligibleForReviewedEvidence:reasons.length===2&&
        reasons.includes('SEMANTIC_SUPPORT_NOT_VERIFIED'),
      decision:reasons.includes('SOURCE_EXCLUDED_BY_OWNER')?'REFUSE':'INCONCLUSIVE',
      reasons
    };
  });
  const explicitlyExcluded=observations.some(o=>o.reasons.includes('SOURCE_EXCLUDED_BY_OWNER'));
  return {
    schema:'qualityrag.drive-governed-candidate-check/v1',
    result:explicitlyExcluded?'REFUSE':'INCONCLUSIVE',
    decisionBoundary:'OWNER_SOURCE_CONTROL_AND_PACKSPEC_MEMBERSHIP_ONLY',
    evaluationAdmitted:false,meaningVerified:false,
    independentProvenanceVerified:false,
    asOf:new Date(this.now()).toISOString(),
    policy:{id:policy.id,version:policy.version,sha256:policySha256},
    index:{
      selectedFolder:connection?.folderId||null,
      asOf:snapshot?.syncedAt||null,
      coverage:snapshot?.coverage||'UNKNOWN',
      freshness:fresh?'CURRENT':'NOT_CURRENT'
    },
    counters:{
      submitted:candidates.length,
      ownerExcluded:observations.filter(o=>o.reasons.includes('SOURCE_EXCLUDED_BY_OWNER')).length,
      eligibleForReview:observations.filter(o=>o.eligibleForReviewedEvidence).length,
      otherUnresolved:observations.filter(o=>!o.eligibleForReviewedEvidence&&
        !o.reasons.includes('SOURCE_EXCLUDED_BY_OWNER')).length
    },
    observations
  };
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
    if(source.searchEnabled===false)continue;
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
