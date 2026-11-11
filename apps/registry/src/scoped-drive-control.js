// Narrow owner-scoped Drive routes. OAuth lifecycle requires explicit OIDC-backed injection.
// Only enabled when both trusted OIDC and injected Drive components exist.
const PREFIX='/v1/drives/google/';
const ROUTES=new Set(['status','index','visibility','source-control','sync','clear-index',
 'start','folders','folder','files','disconnect','search']);
function send(res,status,payload){
 res.writeHead(status,{'content-type':'application/json; charset=utf-8',
  'cache-control':'no-store','x-content-type-options':'nosniff'});
 res.end(JSON.stringify(payload));
}
function safe(code){
 return ['DRIVE_CONNECTION_NOT_FOUND','DRIVE_FOLDER_NOT_CONFIGURED',
  'DRIVE_INDEX_NOT_FOUND','DRIVE_INDEX_INTEGRITY_FAILURE',
  'DRIVE_STORAGE_INTEGRITY_FAILURE','DRIVE_SYNC_IN_PROGRESS',
  'DRIVE_SYNC_INVALIDATED','DRIVE_SOURCE_NOT_FOUND',
  'INVALID_DRIVE_SOURCE_CONTROL','DRIVE_INDEX_DIRECTORY_REQUIRED',
  'DRIVE_AUTHORIZATION_REQUIRED','GOOGLE_DRIVE_UNAVAILABLE',
  'DRIVE_RATE_LIMITED','DRIVE_FOLDER_NOT_FOUND','INVALID_DRIVE_FOLDER_ID',
  'INVALID_DRIVE_PAGE_TOKEN','DRIVE_OAUTH_TOO_MANY_PENDING',
  'INVALID_DRIVE_SEARCH_QUERY','DRIVE_SHARED_CONTROL_CONFLICT',
  'DRIVE_SHARED_INDEX_NOT_READY','DRIVE_SYNC_CHECKPOINT_CONFLICT'].includes(code)?
    code:'DRIVE_OPERATION_FAILED';
}
// Google redirects cannot attach the caller's OIDC bearer token. The manager
// validates the single-use high-entropy state bound to the OIDC subject at start.
export async function handleDriveOauthCallback(req,res,{url,authenticate,driveManager,driveIndex}){
 if(url.pathname!=='/v1/drives/google/callback')return false;
 if(req.method!=='GET'||!authenticate||!driveManager||!driveIndex){
  send(res,404,{error:'DRIVE_CONNECT_DISABLED'});return true;
 }
 let succeeded=false;
 try{
  if([...url.searchParams.keys()].some(k=>!['state','code','error'].includes(k))||
     url.searchParams.getAll('state').length!==1||
     url.searchParams.getAll('code').length>1||
     url.searchParams.getAll('error').length>1)throw Error('DRIVE_OAUTH_STATE_INVALID');
  const state=url.searchParams.get('state');
  if(typeof state!=='string'||state.length<20||state.length>120)
   throw Error('DRIVE_OAUTH_STATE_INVALID');
  const completed=await driveManager.callback({
   state,code:url.searchParams.get('code'),error:url.searchParams.get('error')
  });
  if(!completed||typeof completed.subject!=='string'||!completed.subject.trim())
   throw Error('DRIVE_OAUTH_SUBJECT_MISMATCH');
  // A new account connection invalidates any previously indexed source scope.
  await driveIndex.clearCoordinated(completed.subject);
  succeeded=true;
 }catch{ /* Do not reflect provider error, state or authorization code. */ }
 // This origin is configured and validated by the manager, never read from URL.
 const origin=driveManager.studioOrigin;
 if(typeof origin!=='string'||!/^https:\/\/[^/?#]+$/.test(origin)&&
    !/^http:\/\/(?:localhost|127\.0\.0\.1)(?::[0-9]+)?$/.test(origin)){
  send(res,503,{error:'DRIVE_CONNECT_DISABLED'});return true;
 }
 res.writeHead(303,{location:origin+'/?drive='+(succeeded?'connected':'authorization-failed'),
  'cache-control':'no-store','referrer-policy':'no-referrer'});
 res.end();return true;
}

export async function handleScopedDriveControl(req,res,{pathname,actor,authenticate,
  driveManager,driveIndex,parseBody,url}){
 if(!pathname.startsWith(PREFIX))return false;
 const route=pathname.slice(PREFIX.length);
 if(!ROUTES.has(route))return false;
 // Preserve the existing server authorization check; this is defense in depth.
 if(!authenticate||!driveManager||!driveIndex){
  send(res,404,{error:'DRIVE_CONNECT_DISABLED'});return true;
 }
 if(typeof actor!=='string'||!actor.trim()){
  send(res,401,{error:'UNAUTHORIZED'});return true;
 }
 const method=['source-control','sync','clear-index','start','folder','disconnect','search'].includes(route)?'POST':'GET';
 if(req.method!==method){send(res,404,{error:'NOT_FOUND'});return true}
 try{
  const conn=driveManager.status(actor);
  // Legacy synchronous previews are local-only; do not present them as
  // authoritative after the encrypted index moves to shared PostgreSQL.
  if(driveIndex.cursorCoordinator&&
    ['status','index','visibility','search'].includes(route)){
    send(res,503,{error:'DRIVE_SHARED_READ_ADAPTER_PENDING',
      sourceTruth:'UNKNOWN',releasePermitted:false});return true;
  }
  let result;
  if(route==='status')result={...conn,indexEnabled:true,index:driveIndex.status(actor,conn)};
  else if(route==='index')result=driveIndex.status(actor,conn);
  else if(route==='visibility')result=driveIndex.visibility(actor,conn);
  else if(route==='start')result=driveManager.start(actor);
  else if(route==='folders')result=await driveManager.folders(actor,
    url?.searchParams.get('parentId')||'root',url?.searchParams.get('pageToken')||null);
  else if(route==='folder'){
   const data=await parseBody(req);
   if(!data||typeof data!=='object'||Array.isArray(data)||
      Object.keys(data).length!==1||typeof data.folderId!=='string')
    throw Error('INVALID_DRIVE_FOLDER_ID');
   const oldFolder=conn.folderId;
   result=await driveManager.selectFolder(actor,data.folderId);
   if(oldFolder!==result.folderId)await driveIndex.clearCoordinated(actor);
  }
  else if(route==='files')result=await driveManager.selectedFiles(actor);
  else if(route==='search'){
   const data=await parseBody(req);
   if(!data||typeof data!=='object'||Array.isArray(data)||
      Object.keys(data).length!==1||typeof data.query!=='string')
    throw Error('INVALID_DRIVE_SEARCH_QUERY');
   result=driveIndex.search(actor,conn,data.query);
  }
  else if(route==='disconnect'){
   await driveIndex.clearCoordinated(actor);result=await driveManager.disconnect(actor);
  }
  else if(route==='source-control'){
   const data=await parseBody(req);
   if(!data||typeof data!=='object'||Array.isArray(data)||
      Object.keys(data).some(key=>!['sourceId','searchable','reason'].includes(key)))
     throw Error('INVALID_DRIVE_SOURCE_CONTROL');
   result=driveIndex.cursorCoordinator?
     await driveIndex.controlSharedSource(actor,conn,data):
     driveIndex.controlSource(actor,conn,data);
  }else if(route==='sync')result=await driveIndex.sync(actor,driveManager);
  else result=await driveIndex.clearCoordinated(actor);
  send(res,200,result);return true;
 }catch(error){
  const code=safe(error?.message);
  const status=code==='INVALID_DRIVE_SOURCE_CONTROL'?400:
    code==='DRIVE_CONNECTION_NOT_FOUND'||code==='DRIVE_FOLDER_NOT_CONFIGURED'||
    code==='DRIVE_INDEX_NOT_FOUND'||code==='DRIVE_SYNC_IN_PROGRESS'||
    code==='DRIVE_SYNC_INVALIDATED'||
    code==='DRIVE_SHARED_CONTROL_CONFLICT'||
    code==='DRIVE_SHARED_INDEX_NOT_READY'||
    code==='DRIVE_SYNC_CHECKPOINT_CONFLICT'?409:
    code==='DRIVE_AUTHORIZATION_REQUIRED'?403:400;
  send(res,status,{error:code});return true;
 }
}
