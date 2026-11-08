// Google Drive read-only inventory adapter. Authentication, tenant ACL checks and
// credential storage belong to the caller; this module never receives refresh tokens.
const API='https://www.googleapis.com/drive/v3/files';
const FIELDS='nextPageToken,incompleteSearch,files(id,name,mimeType,modifiedTime,version,md5Checksum,trashed,parents,webViewLink,owners(emailAddress),permissions(id,type,role,emailAddress,domain,allowFileDiscovery))';
export async function inventoryGoogleDrive({accessToken,fetchImpl=fetch,pageLimit=20,signal}={}){
 if(typeof accessToken!=='string'||!accessToken.trim())throw new Error('GOOGLE_ACCESS_TOKEN_REQUIRED');
 if(!Number.isInteger(pageLimit)||pageLimit<1||pageLimit>100)throw new Error('INVALID_PAGE_LIMIT');
 const files=[];let nextPageToken,complete=false;const seen=new Set();
 for(let page=0;page<pageLimit;page++){
  const u=new URL(API);
  u.searchParams.set('q','trashed = false');u.searchParams.set('fields',FIELDS);
  u.searchParams.set('pageSize','1000');u.searchParams.set('supportsAllDrives','true');
  u.searchParams.set('includeItemsFromAllDrives','true');
  if(nextPageToken)u.searchParams.set('pageToken',nextPageToken);
  const response=await fetchImpl(u.toString(),{headers:{Authorization:'Bearer '+accessToken,Accept:'application/json'},signal});
  if(!response.ok)throw new Error('GOOGLE_DRIVE_HTTP_'+response.status);
  const data=await response.json();
  if(!data||!Array.isArray(data.files)||data.incompleteSearch)throw new Error('GOOGLE_DRIVE_INCOMPLETE_SEARCH');
  for(const f of data.files){
   if(!f||typeof f.id!=='string'||!f.id||typeof f.mimeType!=='string')throw new Error('GOOGLE_DRIVE_INVALID_FILE');
   if(f.trashed)continue;
   if(seen.has(f.id))continue;seen.add(f.id);
   files.push({source_id:'google-drive:'+f.id,provider:'google',provider_id:f.id,name:f.name||'',mime_type:f.mimeType,
    revision:f.version||f.md5Checksum||f.modifiedTime||null,modified_at:f.modifiedTime||null,
    parent_ids:f.parents||[],owner_emails:(f.owners||[]).map(o=>o.emailAddress).filter(Boolean),
    permissions:f.permissions||[],web_url:f.webViewLink||null});
  }
  nextPageToken=data.nextPageToken;
  if(!nextPageToken){complete=true;break;}
 }
 return {files,complete,truncated:!complete,next_page_token:nextPageToken||null};
}

// Explicit MIME routing avoids treating Google Workspace native files as binary downloads.
export function googleExportMime(mime){
 return ({'application/vnd.google-apps.document':'text/plain',
  'application/vnd.google-apps.spreadsheet':'text/csv',
  'application/vnd.google-apps.presentation':'text/plain'})[mime]||null;
}
