// Narrow, owner-scoped Registry control routes. No Google OAuth/callback activation.
// Only enabled when both trusted OIDC and injected Drive components exist.
const PREFIX='/v1/drives/google/';
const ROUTES=new Set(['status','index','visibility','source-control','sync','clear-index']);
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
  'DRIVE_RATE_LIMITED'].includes(code)?code:'DRIVE_OPERATION_FAILED';
}
export async function handleScopedDriveControl(req,res,{pathname,actor,authenticate,
  driveManager,driveIndex,parseBody}){
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
 const method=route==='source-control'||route==='sync'||route==='clear-index'?'POST':'GET';
 if(req.method!==method){send(res,404,{error:'NOT_FOUND'});return true}
 try{
  const conn=driveManager.status(actor);
  let result;
  if(route==='status')result={...conn,indexEnabled:true,index:driveIndex.status(actor,conn)};
  else if(route==='index')result=driveIndex.status(actor,conn);
  else if(route==='visibility')result=driveIndex.visibility(actor,conn);
  else if(route==='source-control'){
   const data=await parseBody(req);
   if(!data||typeof data!=='object'||Array.isArray(data)||
      Object.keys(data).some(key=>!['sourceId','searchable','reason'].includes(key)))
     throw Error('INVALID_DRIVE_SOURCE_CONTROL');
   result=driveIndex.controlSource(actor,conn,data);
  }else if(route==='sync')result=await driveIndex.sync(actor,driveManager);
  else result=driveIndex.clear(actor);
  send(res,200,result);return true;
 }catch(error){
  const code=safe(error?.message);
  const status=code==='INVALID_DRIVE_SOURCE_CONTROL'?400:
    code==='DRIVE_CONNECTION_NOT_FOUND'||code==='DRIVE_FOLDER_NOT_CONFIGURED'||
    code==='DRIVE_INDEX_NOT_FOUND'||code==='DRIVE_SYNC_IN_PROGRESS'||
    code==='DRIVE_SYNC_INVALIDATED'?409:
    code==='DRIVE_AUTHORIZATION_REQUIRED'?403:400;
  send(res,status,{error:code});return true;
 }
}
