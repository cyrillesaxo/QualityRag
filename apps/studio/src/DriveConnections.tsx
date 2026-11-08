import React,{useCallback,useEffect,useState} from 'react';
import {DriveTrustControls} from './DriveTrustControls';

type Connection={provider:'google_drive';connected:boolean;email?:string;displayName?:string;
  folderId:string|null;folderName:string|null;indexed:boolean;ingestionStatus:string;
  sourceScope?:string;note?:string;indexEnabled?:boolean;index?:DriveIndexStatus|null};
type DriveIndexStatus={indexed:boolean;sourceCount:number;lastSyncedAt?:string;
  syncStatus:string;coverage:string;summary?:{listed:number;eligible:number;indexed:number;
  unsupported:number;failed:number;tooLarge:number;excludedEmpty:number;truncatedLines:number}};
type DriveHit={source_id:string;revision:string;source_url:string;file_name:string;mime_type:string;
  anchor:{kind:string;line_number:number};field:string;matched_text:string;
  matching_terms:number;quality:string};
type DriveSearch={hits:DriveHit[];indexed:boolean;coverage:string;reason?:string;
  truncated?:boolean;sourceCount?:number;lastSyncedAt?:string};
type Folder={id:string;name:string};
type FileRow={id:string;name:string;mimeType:string;modifiedTime:string|null;size:string|null};
const messageOrigin=()=>window.location.origin;
function DriveConnections({token,serviceId,environment}:{token:string;serviceId:string;environment:string}){
 const [connection,setConnection]=useState<Connection|null>(null);
 const [error,setError]=useState('');
 const [loading,setLoading]=useState(false);
 const [authUrl,setAuthUrl]=useState('');
 const [folders,setFolders]=useState<Folder[]>([]);
 const [parentId,setParentId]=useState('root');
 const [currentName,setCurrentName]=useState('My Drive');
 const [browsing,setBrowsing]=useState(false);
 const [parents,setParents]=useState<{id:string;name:string}[]>([]);
 const [pageToken,setPageToken]=useState<string|null>(null);
 const [files,setFiles]=useState<FileRow[]>([]);
 const [filesTruncated,setFilesTruncated]=useState(false);
 const [driveQuery,setDriveQuery]=useState('');
 const [driveResults,setDriveResults]=useState<DriveSearch|null>(null);
 const [indexFeedback,setIndexFeedback]=useState('');
 const [unsupported,setUnsupported]=useState(false);
 const api=useCallback(async(route:string,method='GET',payload?:unknown)=>{
   if(!token)throw new Error('Sign in with your registry OIDC token first.');
   const response=await fetch(route,{method,headers:{
     Authorization:'Bearer '+token,'Content-Type':'application/json'
   },body:payload===undefined?undefined:JSON.stringify(payload),
     redirect:'error',cache:'no-store'});
   let result;
   try{result=await response.json()}catch{throw new Error('Drive service returned an invalid response.')}
   if(!response.ok)throw new Error(String(result.error||'Drive operation failed'));
   return result;
 },[token]);
 const refresh=useCallback(async()=>{
   if(!token){setConnection(null);setFolders([]);setFiles([]);setDriveResults(null);return;}
   try{
     const data=await api('/v1/drives/google/status');
     setConnection(data);setUnsupported(false);setError('');
   }catch(e){
     setConnection(null);setFolders([]);setFiles([]);setDriveResults(null);
     setUnsupported(String(e).includes('NOT_FOUND')||String(e).includes('DRIVE_CONNECT_DISABLED'));
     setError(String(e));
   }
 },[api,token]);
 useEffect(()=>{setConnection(null);setAuthUrl('');setFolders([]);
   setFiles([]);setDriveResults(null);setIndexFeedback('');setParents([]);setParentId('root');setCurrentName('My Drive');
   setBrowsing(false);setPageToken(null);refresh();
 },[refresh]);
 useEffect(()=>{
   function receive(event:MessageEvent){
     if(event.origin!==messageOrigin()||event.data?.type!=='qualityrag-drive-oauth-result')return;
     if(event.data.status==='connected')refresh();
     else setError('Google authorization was declined or could not be completed.');
   }
   window.addEventListener('message',receive);
   const param=new URLSearchParams(window.location.search).get('drive');
   if(window.opener&&(param==='connected'||param==='authorization-failed')){
     window.opener.postMessage({type:'qualityrag-drive-oauth-result',status:param},
       window.location.origin);
     window.close();
   }
   return()=>window.removeEventListener('message',receive);
 },[refresh]);
 async function connect(){
   if(!token)return;
   // Open synchronously so the browser allows the user-initiated OAuth popup.
   const popup=window.open('about:blank','qualityrag-google-drive-connect',
     'popup=yes,width=620,height=760');
   setLoading(true);setAuthUrl('');setError('');
   try{
     const result=await api('/v1/drives/google/start','POST');
     const url=new URL(result.authorizationUrl);
     if(url.origin!=='https://accounts.google.com')throw Error('Unexpected OAuth provider.');
     if(popup){popup.location.href=url.toString();}
     else{setAuthUrl(url.toString());setError('Popup blocked: use the authorization link below.');}
   }catch(e){if(popup)popup.close();setError(String(e))}
   finally{setLoading(false)}
 }
 async function browse(id:string,name:string,previous?:{id:string;name:string}[]){
   if(!token)return;
   setLoading(true);
   try{
     const q=new URLSearchParams({parentId:id});
     const result=await api('/v1/drives/google/folders?'+q);
     setFolders(result.folders||[]);setPageToken(result.nextPageToken||null);
     setParentId(id);setCurrentName(name);setParents(previous||[]);setBrowsing(true);setError('');
   }catch(e){setError(String(e))}finally{setLoading(false)}
 }
 async function select(){
   setLoading(true);
   try{
     const updated=await api('/v1/drives/google/folder','POST',{folderId:parentId});
     setConnection(updated);setDriveResults(null);setIndexFeedback('');setError('');
     await preview();
   }catch(e){setError(String(e))}finally{setLoading(false)}
 }
 async function preview(){
   setLoading(true);
   try{
     const data=await api('/v1/drives/google/files');
     setFiles(data.files||[]);setFilesTruncated(Boolean(data.truncated));setError('');
   }catch(e){setError(String(e));setFiles([])}finally{setLoading(false)}
 }
 async function nextPage(){
   if(!pageToken)return;
   setLoading(true);
   try{
     const q=new URLSearchParams({parentId,pageToken});
     const result=await api('/v1/drives/google/folders?'+q);
     setFolders(old=>[...old,...(result.folders||[])].slice(0,100));
     setPageToken(result.nextPageToken||null);
   }catch(e){setError(String(e))}finally{setLoading(false)}
 }
 async function syncSelected(){
   setLoading(true);setDriveResults(null);setIndexFeedback('');setError('');
   try{
     const result=await api('/v1/drives/google/sync','POST',{});
     setIndexFeedback('Indexed '+result.sourceCount+' text files. Coverage: '+result.coverage+
       '. Unsupported, failed and truncated files are not searchable.');
     await refresh();
   }catch(e){setError(String(e))}
   finally{setLoading(false)}
 }
 async function searchIndex(){
   setLoading(true);setDriveResults(null);setIndexFeedback('');setError('');
   try{
     const result=await api('/v1/drives/google/search','POST',{query:driveQuery});
     setDriveResults(result);
     setIndexFeedback(result.reason==='SYNC_REQUIRED'?
       'Index is stale. Sync again before relying on search results.':
       result.hits.length+' matching source passages found; no PackSpec admission performed.');
   }catch(e){setError(String(e))}
   finally{setLoading(false)}
 }
 async function clearIndex(){
   if(!window.confirm('Delete this Drive text index? Your Google Drive files are not changed.'))return;
   setLoading(true);
   try{
     await api('/v1/drives/google/clear-index','POST',{});
     setDriveResults(null);setIndexFeedback('Local text index erased. Google Drive files remain untouched.');
     await refresh();
   }catch(e){setError(String(e))}
   finally{setLoading(false)}
 }
 async function disconnect(){
   if(!window.confirm('Disconnect this Google Drive account from your QualityRAG profile?'))return;
   setLoading(true);
   try{
     const result=await api('/v1/drives/google/disconnect','POST');
     setConnection({provider:'google_drive',connected:false,folderId:null,folderName:null,
       indexed:false,ingestionStatus:'NOT_CONFIGURED'});
     setFolders([]);setFiles([]);setDriveResults(null);setIndexFeedback('');setAuthUrl('');
     setError(result.externalRevocationUnconfirmed?
       'Local credential deleted. Google grant revocation could not be confirmed; check your Google Account permissions.':'');
   }catch(e){setError(String(e))}finally{setLoading(false)}
 }
 return <section className="panel" aria-label="Personal cloud drive connections" style={{borderTop:'4px solid #038112'}}>
   <h2>My cloud drives</h2>
   <p>Connect your own account. QualityRAG never shares a Drive authorization between users.
     Choose a folder this local Studio preview can list.</p>
   <p style={{fontSize:13,color:'#8b5c21'}}><strong>Google permission disclosure:</strong>
     Google requests read-only access to your <em>whole Drive</em>, not a folder-scoped OAuth grant.
     Connecting alone lists metadata only; explicit text synchronization can download
     selected-folder content into an encrypted local index.
     Do not connect a confidential Drive to an unreviewed deployment.</p>
   <p style={{fontSize:13}}><strong>Google Drive:</strong> read-only connection and folder selection.
     <span style={{marginLeft:10,color:'#587064'}}>OneDrive / Dropbox adapters: not yet implemented.</span></p>
   {!token&&<p role="status">Connect with your OIDC bearer token above to configure your Drive.</p>}
   {token&&unsupported&&<p role="status">Cloud Drive is not configured on this registry.
     An administrator must enable per-user OIDC and the Google OAuth client on the server.</p>}
   {token&&!unsupported&&<div>
     <div className="line">
       {connection?.connected?
         <span><strong>Connected:</strong> {connection.email} (this user only)</span>:
         <span>Google Drive not connected</span>}
       <button type="button" onClick={refresh} disabled={loading}>Refresh status</button>
       {!connection?.connected?
         <button type="button" onClick={connect} disabled={loading}>Connect my Google Drive</button>:
         <button type="button" onClick={disconnect} disabled={loading}>Disconnect</button>}
     </div>
     {authUrl&&<p><a href={authUrl} target="_blank" rel="noreferrer">Continue authorization on Google</a>
       <span> (then return and refresh the connection status)</span></p>}
     {connection?.connected&&<>
       <p><strong>Selected folder:</strong> {connection.folderName||'Not chosen'}
         {connection.folderId&&<code> ({connection.folderId})</code>}
       </p>
       <div className="line">
         <button type="button" disabled={loading} onClick={()=>browse('root','My Drive',[])}>
           Browse folders
         </button>
         <button type="button" disabled={loading||!connection.folderId} onClick={preview}>
           Preview permitted files
         </button>
       </div>
       {browsing&&
         <div style={{border:'1px solid #d3e3d5',padding:15,borderRadius:12,marginTop:12}}>
           <p>Choose a folder in your own Drive. Current location:
             <strong> {currentName} </strong></p>
           {parents.length>0&&<button type="button" disabled={loading} onClick={()=>{
             const previous=parents[parents.length-1];
             browse(previous.id,previous.name,parents.slice(0,-1));
           }}>Back</button>}
           <ul>{folders.map(folder=><li key={folder.id}>
             <button type="button" disabled={loading} onClick={()=>browse(folder.id,folder.name,
               [...parents,{id:parentId,name:currentName}])}>
               Open folder: {folder.name}
             </button>
           </li>)}</ul>
           {pageToken&&<button type="button" disabled={loading} onClick={nextPage}>More folders</button>}
           <button type="button" disabled={loading} onClick={select}>Use this folder</button>
         </div>}
       {files.length>0&&<>
         <h3>Selected-folder files (metadata only)</h3>
         <ul>{files.map(file=><li key={file.id}>
           {file.name} <code>{file.mimeType}</code>
         </li>)}</ul>
         {filesTruncated&&<p role="status">More than 100 entries. The preview is truncated.</p>}
       </>}
       <div style={{border:'1px solid #cfe4d1',background:'#f6fbf7',
         padding:18,borderRadius:13,marginTop:18}} aria-label="My private Drive text index">
         <h3>My private Drive text index</h3>
         <p>Explicit, read-only synchronization of this folder's Google Docs, TXT, Markdown,
           CSV and JSON files. Text is stored encrypted in an OIDC-user-specific local index,
           never in the shared Semantic Store worker.</p>
         <p><strong>Index:</strong> {connection.index?.syncStatus||'Not enabled'}
           {' · '} <strong>Sources:</strong> {connection.index?.sourceCount||0}
           {' · '} <strong>Coverage:</strong> {connection.index?.coverage||'UNKNOWN'}
         </p>
         {connection.index?.summary&&<p style={{fontSize:13}}>Listed:
           {connection.index.summary.listed} · Indexed: {connection.index.summary.indexed} ·
           Unsupported: {connection.index.summary.unsupported} ·
           Failed: {connection.index.summary.failed} ·
           Too large: {connection.index.summary.tooLarge} ·
           Truncated: {connection.index.summary.truncatedLines}
         </p>}
         {!connection.indexEnabled?
           <p role="status">Private indexing is disabled by the registry operator.
             Configure QUALITYRAG_DRIVE_INDEX_DIR to opt in.</p>:
           <>
             <div className="line">
               <button type="button" disabled={loading||!connection.folderId||
                 connection.folderId==='root'} onClick={syncSelected}>Sync selected folder now</button>
               <button type="button" disabled={loading||!connection.index?.indexed}
                 onClick={clearIndex}>Delete my local index</button>
             </div>
             {connection.folderId==='root'&&<p role="status">Choose a specific folder to enable indexing.
               Indexing the entire My Drive root is blocked.</p>}
             <div className="line">
               <label>Search my indexed documents
                 <input value={driveQuery} onChange={e=>setDriveQuery(e.target.value)}
                   placeholder="contract exception" aria-label="Private Drive text search"/></label>
               <button type="button" disabled={loading||!connection.index?.indexed||
                 !driveQuery.trim()} onClick={searchIndex}>Search my index</button>
             </div>
             {indexFeedback&&<p role="status">{indexFeedback}</p>}
             {driveResults&&<>
               {driveResults.truncated&&<p role="alert">Only the first 30 matches are shown.</p>}
               <ul>{driveResults.hits.map((hit,i)=><li key={hit.source_id+'#'+hit.anchor.line_number+'#'+i}>
                 <strong>{hit.file_name}</strong> · Line {hit.anchor.line_number}
                 {' · '} revision <code>{hit.revision.slice(0,12)}…</code>
                 <p>{hit.matched_text}</p>
                 <a href={hit.source_url} target="_blank" rel="noopener noreferrer">
                   Open original in my Google Drive
                 </a>
               </li>)}</ul>
               <p><strong>Lexical matches, not verified evidence.</strong> Line anchors refer to the
                 extracted plain-text representation; Google Docs may not display the same line numbers.
                 Empty results do
                 not establish that the source condition is absent.</p>
             </>}
           </>}
       </div>
       <DriveTrustControls token={token} folderId={connection.folderId}
         connected={connection.connected} indexEnabled={Boolean(connection.indexEnabled)}
         serviceId={serviceId} environment={environment}
         lastSyncedAt={connection.index?.lastSyncedAt}/>
       <p style={{fontSize:13,color:'#526d56'}}>
         Drive connection alone downloads no content. Only the explicit
         “Sync selected folder now” action downloads eligible text into this user's encrypted index.
         No cloud content is automatically admitted into a PackSpec.
       </p>
     </>}
   </div>}
   {error&&<p className="status" role="alert">{error}</p>}
 </section>;
}
export {DriveConnections};
