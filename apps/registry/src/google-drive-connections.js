import fs from 'node:fs';
import path from 'node:path';
import {randomBytes, createHash, createCipheriv, createDecipheriv} from 'node:crypto';

const DRIVE_SCOPE='https://www.googleapis.com/auth/drive.readonly';
const GOOGLE_AUTH='https://accounts.google.com/o/oauth2/v2/auth';
const GOOGLE_TOKEN='https://oauth2.googleapis.com/token';
const GOOGLE_REVOKE='https://oauth2.googleapis.com/revoke';
const GOOGLE_DRIVE='https://www.googleapis.com/drive/v3';
const SAFE_ID=/^[a-zA-Z0-9_-]{1,200}$/;
const VALID_USER=/^[^\s@]{1,200}@[^\s@]{1,200}$/;
const MAX_FILE_BYTES=250_000;

const b64url=bytes=>Buffer.from(bytes).toString('base64url');
const digest=str=>createHash('sha256').update(str).digest('hex');
const fail=(reason)=>{throw Error(reason)};
const assert=(condition,reason)=>{if(!condition)fail(reason)};
const authKeys = ['access_token','refresh_token','expires_at','email','display_name','folder_id','folder_name'];

function strictJson(data){
  assert(typeof data==='string'&&data.length<MAX_FILE_BYTES,'INVALID_DRIVE_RESPONSE');
  let result;
  try{result=JSON.parse(data)}catch{fail('INVALID_DRIVE_RESPONSE')}
  assert(result&&typeof result==='object'&&!Array.isArray(result),'INVALID_DRIVE_RESPONSE');
  return result;
}
function googleError(response) {
  if(response.status===401||response.status===403)fail('DRIVE_AUTHORIZATION_REQUIRED');
  if(response.status===429)fail('DRIVE_RATE_LIMITED');
  fail('GOOGLE_DRIVE_UNAVAILABLE');
}
function validateOrigin(value,field){
  const url=new URL(value);
  assert(!url.username&&!url.password&&!url.search&&!url.hash&&
    !url.pathname.replace(/\/$/,'')&&
    (url.protocol==='https:'||
      (url.protocol==='http:'&&['localhost','127.0.0.1'].includes(url.hostname))),
      'INVALID_DRIVE_'+field);
  return url.origin;
}
function validateRedirect(value){
  const url=new URL(value);
  assert(!url.username&&!url.password&&!url.search&&!url.hash&&
    url.pathname==='/v1/drives/google/callback'&&
    (url.protocol==='https:'||
    (url.protocol==='http:'&&['localhost','127.0.0.1'].includes(url.hostname))),
    'INVALID_DRIVE_REDIRECT');
  return url.toString();
}
function validateKey(raw){
  assert(typeof raw==='string'&&raw.length>=43,'DRIVE_ENCRYPTION_KEY_REQUIRED');
  const bytes=Buffer.from(raw,'base64');
  assert(bytes.length===32&&bytes.toString('base64')===raw,'INVALID_DRIVE_ENCRYPTION_KEY');
  return bytes;
}
function validateSubject(subject){
  assert(typeof subject==='string'&&subject.length>1&&subject.length<=300,'DRIVE_AUTHENTICATED_SUBJECT_REQUIRED');
  return subject;
}
function validateFolderId(id){
  assert(typeof id==='string'&&SAFE_ID.test(id),'INVALID_DRIVE_FOLDER_ID');
  return id;
}
function safeError(error){
  return ['GOOGLE_DRIVE_UNAVAILABLE','DRIVE_AUTHORIZATION_REQUIRED','DRIVE_RATE_LIMITED',
    'GOOGLE_OAUTH_FAILED','DRIVE_CONNECTION_NOT_FOUND','DRIVE_FOLDER_NOT_CONFIGURED',
    'INVALID_DRIVE_FOLDER_ID','INVALID_DRIVE_PAGE_TOKEN','DRIVE_FOLDER_NOT_FOUND',
    'DRIVE_OAUTH_NO_REFRESH_TOKEN','DRIVE_OAUTH_STATE_INVALID','DRIVE_OAUTH_STATE_EXPIRED',
    'DRIVE_OAUTH_SUBJECT_MISMATCH','DRIVE_CONNECT_DISABLED','DRIVE_ACCOUNT_MISMATCH',
    'DRIVE_STORAGE_INTEGRITY_FAILURE'].includes(error?.message)?error.message:'DRIVE_OPERATION_FAILED';
}
export {safeError as safeDriveError};

export class GoogleDriveConnections{
  constructor({file,encryptionKey,clientId,clientSecret,redirectUri,studioOrigin,fetchImpl=fetch,
    now=()=>Date.now()}){
    assert(typeof file==='string'&&file.length>0,'DRIVE_FILE_REQUIRED');
    assert(typeof clientId==='string'&&clientId.length>12,'GOOGLE_CLIENT_ID_REQUIRED');
    assert(typeof clientSecret==='string'&&clientSecret.length>8,'GOOGLE_CLIENT_SECRET_REQUIRED');
    this.file=file;
    this.key=validateKey(encryptionKey);
    this.clientId=clientId;this.clientSecret=clientSecret;
    this.redirectUri=validateRedirect(redirectUri);
    this.studioOrigin=validateOrigin(studioOrigin,'STUDIO_ORIGIN');
    this.fetch=fetchImpl;this.now=now;
    this.pending=new Map();
    this.records=this.load();
  }
  load(){
    if(!fs.existsSync(this.file))return {};
    const meta=fs.lstatSync(this.file);
    assert(meta.isFile()&&!meta.isSymbolicLink()&&(meta.mode&0o077)===0,
      'DRIVE_STORAGE_INTEGRITY_FAILURE');
    const bytes=fs.readFileSync(this.file,'utf8');
    assert(bytes.length<=1_000_000,'DRIVE_STORAGE_INTEGRITY_FAILURE');
    const records=strictJson(bytes);
    assert(Object.keys(records).every(k=>/^[0-9a-f]{64}$/.test(k)),'DRIVE_STORAGE_INTEGRITY_FAILURE');
    return records;
  }
  save(){
    fs.mkdirSync(path.dirname(this.file),{recursive:true,mode:0o700});
    const tmp=this.file+'.'+process.pid+'.'+b64url(randomBytes(6))+'.tmp';
    try{
      fs.writeFileSync(tmp,JSON.stringify(this.records),{mode:0o600,flag:'wx'});
      fs.renameSync(tmp,this.file);
    }catch(e){try{fs.unlinkSync(tmp)}catch{};throw e}
  }
  encrypt(subject,data){
    const iv=randomBytes(12);
    const cipher=createCipheriv('aes-256-gcm',this.key,iv);
    cipher.setAAD(Buffer.from('qualityrag.user-drive/v1:'+subject));
    const payload=Buffer.concat([cipher.update(JSON.stringify(data),'utf8'),cipher.final()]);
    return {v:1,iv:b64url(iv),ct:b64url(payload),tag:b64url(cipher.getAuthTag())};
  }
  decrypt(subject){
    const record=this.records[digest(subject)];
    if(!record)return null;
    try{
      assert(record.v===1,'DRIVE_STORAGE_INTEGRITY_FAILURE');
      const decipher=createDecipheriv('aes-256-gcm',this.key,Buffer.from(record.iv,'base64url'));
      decipher.setAAD(Buffer.from('qualityrag.user-drive/v1:'+subject));
      decipher.setAuthTag(Buffer.from(record.tag,'base64url'));
      const decoded=JSON.parse(Buffer.concat([decipher.update(Buffer.from(record.ct,'base64url')),
        decipher.final()]).toString('utf8'));
      assert(authKeys.every(k=>Object.hasOwn(decoded,k)),'DRIVE_STORAGE_INTEGRITY_FAILURE');
      return decoded;
    }catch{fail('DRIVE_STORAGE_INTEGRITY_FAILURE')}
  }
  replace(subject,data){
    this.records[digest(subject)]=this.encrypt(subject,data);
    this.save();
  }
  status(subject){
    subject=validateSubject(subject);
    const stored=this.decrypt(subject);
    return stored?{
      provider:'google_drive',connected:true,
      email:stored.email,displayName:stored.display_name,
      folderId:stored.folder_id,folderName:stored.folder_name,
      canBrowse:true,canReadContent:true,
      indexed:false,ingestionStatus:'NOT_CONFIGURED',
      sourceScope:'selected-folder-only',
      note:'Read-only access. Files are not downloaded or indexed by connecting.'
    }:{provider:'google_drive',connected:false,folderId:null,folderName:null,
       indexed:false,ingestionStatus:'NOT_CONFIGURED'};
  }
  start(subject){
    subject=validateSubject(subject);
    // A bounded one-time state and PKCE verifier; no Google credentials enter the browser.
    const state=b64url(randomBytes(32));
    const verifier=b64url(randomBytes(32));
    const challenge=b64url(createHash('sha256').update(verifier).digest());
    const cutoff=this.now()-10*60_000;
    for(const [key,pending] of this.pending)if(pending.at<cutoff)this.pending.delete(key);
    assert(this.pending.size<2000,'DRIVE_OAUTH_TOO_MANY_PENDING');
    this.pending.set(digest(state),{subject,verifier,at:this.now()});
    const params=new URLSearchParams({
      client_id:this.clientId,redirect_uri:this.redirectUri,response_type:'code',
      scope:DRIVE_SCOPE,access_type:'offline',prompt:'consent',
      include_granted_scopes:'false',
      state,code_challenge:challenge,code_challenge_method:'S256'
    });
    return {authorizationUrl:GOOGLE_AUTH+'?'+params.toString(),
      expiresInSeconds:600,provider:'google_drive',scope:'drive.readonly'};
  }
  async exchange(subject,code,verifier){
    const params=new URLSearchParams({
      client_id:this.clientId,client_secret:this.clientSecret,code,
      redirect_uri:this.redirectUri,grant_type:'authorization_code',code_verifier:verifier
    });
    const response=await this.fetch(GOOGLE_TOKEN,{
      method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:params.toString(),signal:AbortSignal.timeout(8000)
    });
    if(!response.ok)fail('GOOGLE_OAUTH_FAILED');
    const data=strictJson(await response.text());
    assert(typeof data.access_token==='string'&&data.access_token.length>20&&
      typeof data.refresh_token==='string'&&data.refresh_token.length>15&&
      Number.isFinite(data.expires_in),'DRIVE_OAUTH_NO_REFRESH_TOKEN');
    // Drive readonly is a Google restricted scope; allow only the explicitly requested scope.
    if(typeof data.scope==='string'){
      assert(data.scope.split(' ').includes(DRIVE_SCOPE),'GOOGLE_OAUTH_FAILED');
    }
    const about=await this.googleGet(data.access_token,'/about',{'fields':'user(emailAddress,displayName)'});
    const email=about.user?.emailAddress;
    assert(typeof email==='string'&&VALID_USER.test(email),'GOOGLE_OAUTH_FAILED');
    const existing=this.decrypt(subject);
    // A re-consent to a different account cannot silently keep the old selected folder.
    const same=existing?.email===email;
    this.replace(subject,{
      access_token:data.access_token,refresh_token:data.refresh_token,
      expires_at:this.now()+Math.max(30,Number(data.expires_in)-45)*1000,
      email,display_name:typeof about.user.displayName==='string'?about.user.displayName:'',
      folder_id:same?existing.folder_id:null,
      folder_name:same?existing.folder_name:null
    });
  }
  async callback({state,code,error}){
    assert(typeof state==='string'&&state.length<=120,'DRIVE_OAUTH_STATE_INVALID');
    const pending=this.pending.get(digest(state));
    assert(pending,'DRIVE_OAUTH_STATE_INVALID');
    this.pending.delete(digest(state)); // single-use even if Google exchange fails
    assert(this.now()-pending.at<=600_000,'DRIVE_OAUTH_STATE_EXPIRED');
    if(error||typeof code!=='string'||code.length<1||code.length>2500)fail('GOOGLE_OAUTH_FAILED');
    await this.exchange(pending.subject,code,pending.verifier);
    return {connected:true,origin:this.studioOrigin};
  }
  async refresh(subject,stored){
    const params=new URLSearchParams({
      client_id:this.clientId,client_secret:this.clientSecret,
      refresh_token:stored.refresh_token,grant_type:'refresh_token'
    });
    const response=await this.fetch(GOOGLE_TOKEN,{
      method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:params.toString(),signal:AbortSignal.timeout(8000)
    });
    if(!response.ok)fail('DRIVE_AUTHORIZATION_REQUIRED');
    const data=strictJson(await response.text());
    assert(typeof data.access_token==='string'&&data.access_token.length>20&&
      Number.isFinite(data.expires_in),'DRIVE_AUTHORIZATION_REQUIRED');
    const updated={...stored,access_token:data.access_token,
      expires_at:this.now()+Math.max(30,Number(data.expires_in)-45)*1000};
    this.replace(subject,updated);
    return updated.access_token;
  }
  async getToken(subject){
    subject=validateSubject(subject);
    const stored=this.decrypt(subject);
    if(!stored)fail('DRIVE_CONNECTION_NOT_FOUND');
    return stored.expires_at>this.now()+10_000?
      stored.access_token:await this.refresh(subject,stored);
  }
  async googleGet(token,resource,parameters={}){
    const url=new URL(GOOGLE_DRIVE+resource);
    for(const [key,value] of Object.entries(parameters))url.searchParams.set(key,value);
    const response=await this.fetch(url.toString(),{
      method:'GET',headers:{Authorization:'Bearer '+token,Accept:'application/json'},
      signal:AbortSignal.timeout(8000),redirect:'error'
    });
    if(!response.ok)googleError(response);
    return strictJson(await response.text());
  }
  async folders(subject,parentId='root',pageToken=null){
    validateFolderId(parentId);
    assert(pageToken===null||typeof pageToken==='string'&&pageToken.length<=1024&&
      /^[A-Za-z0-9._~+/=-]+$/.test(pageToken),'INVALID_DRIVE_PAGE_TOKEN');
    const token=await this.getToken(subject);
    const query="'"+parentId+"' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false";
    const data=await this.googleGet(token,'/files',{
      q:query,pageSize:'50',fields:'nextPageToken,files(id,name,mimeType,parents)',
      ...(pageToken?{pageToken}:{})
    });
    const folders=(Array.isArray(data.files)?data.files:[]).filter(f=>
      typeof f.id==='string'&&SAFE_ID.test(f.id)&&
      typeof f.name==='string'&&f.mimeType==='application/vnd.google-apps.folder')
      .slice(0,50).map(f=>({id:f.id,name:f.name}));
    return {provider:'google_drive',parentId,folders,
      nextPageToken:typeof data.nextPageToken==='string'?data.nextPageToken:null};
  }
  async selectFolder(subject,folderId){
    validateFolderId(folderId);
    const token=await this.getToken(subject);
    let name='My Drive';
    if(folderId!=='root'){
      const f=await this.googleGet(token,'/files/'+encodeURIComponent(folderId),{
        fields:'id,name,mimeType,trashed'
      });
      assert(f.id===folderId&&f.mimeType==='application/vnd.google-apps.folder'&&
        f.trashed!==true,'DRIVE_FOLDER_NOT_FOUND');
      name=String(f.name||'').slice(0,250);
      assert(name.length>0,'DRIVE_FOLDER_NOT_FOUND');
    }
    const data=this.decrypt(subject);
    data.folder_id=folderId;data.folder_name=name;
    this.replace(subject,data);
    return this.status(subject);
  }
  supportsText(mimeType){
    return new Set([
      'text/plain','text/markdown','text/csv','application/json',
      'application/vnd.google-apps.document'
    ]).has(mimeType);
  }
  async downloadSelectedText(subject,fileId,selectedFolderId,maxBytes=96_000){
    validateFolderId(fileId);
    validateFolderId(selectedFolderId);
    assert(Number.isInteger(maxBytes)&&maxBytes>0&&maxBytes<=96_000,
      'DRIVE_SOURCE_SIZE_INVALID');
    const account=this.decrypt(validateSubject(subject));
    assert(account&&account.folder_id===selectedFolderId&&selectedFolderId!=='root',
      'DRIVE_FOLDER_NOT_CONFIGURED');
    const token=await this.getToken(subject);
    const metadata=await this.googleGet(token,'/files/'+encodeURIComponent(fileId),{
      fields:'id,name,mimeType,parents,trashed,size',supportsAllDrives:'true'
    });
    assert(metadata.id===fileId&&metadata.trashed!==true&&
      Array.isArray(metadata.parents)&&metadata.parents.includes(selectedFolderId),
      'DRIVE_FILE_OUTSIDE_SELECTED_FOLDER');
    assert(this.supportsText(metadata.mimeType),'DRIVE_UNSUPPORTED_FILE_TYPE');
    if(metadata.size!==undefined&&Number(metadata.size)>maxBytes)
      fail('DRIVE_SOURCE_TOO_LARGE');
    const native=metadata.mimeType==='application/vnd.google-apps.document';
    const url=new URL(GOOGLE_DRIVE+'/files/'+encodeURIComponent(fileId)+
      (native?'/export':''));
    if(native)url.searchParams.set('mimeType','text/plain');
    else url.searchParams.set('alt','media');
    const response=await this.fetch(url.toString(),{
      method:'GET',headers:{Authorization:'Bearer '+token,Accept:'text/plain'},
      signal:AbortSignal.timeout(10_000),redirect:'error'
    });
    if(!response.ok)googleError(response);
    const declared=response.headers?.get?.('content-length');
    if(declared&&Number(declared)>maxBytes)fail('DRIVE_SOURCE_TOO_LARGE');
    let result;
    if(response.body?.getReader){
      const reader=response.body.getReader();
      const parts=[];let length=0;
      try{
        while(true){
          const {done,value}=await reader.read();
          if(done)break;
          length+=value.byteLength;
          if(length>maxBytes)fail('DRIVE_SOURCE_TOO_LARGE');
          parts.push(Buffer.from(value));
        }
      }catch(error){try{await reader.cancel()}catch{};throw error}
      result=Buffer.concat(parts,length);
    }else{
      const bytes=await response.arrayBuffer();
      if(bytes.byteLength>maxBytes)fail('DRIVE_SOURCE_TOO_LARGE');
      result=Buffer.from(bytes);
    }
    return result;
  }
  async selectedFiles(subject){
    const data=this.decrypt(validateSubject(subject));
    if(!data)fail('DRIVE_CONNECTION_NOT_FOUND');
    if(!data.folder_id)fail('DRIVE_FOLDER_NOT_CONFIGURED');
    const token=await this.getToken(subject);
    const result=await this.googleGet(token,'/files',{
      q:"'"+data.folder_id+"' in parents and trashed = false",
      pageSize:'100',fields:'nextPageToken,files(id,name,mimeType,modifiedTime,size)',
      orderBy:'name'
    });
    const files=(Array.isArray(result.files)?result.files:[]).filter(f=>
      typeof f.id==='string'&&SAFE_ID.test(f.id)&&typeof f.name==='string')
      .slice(0,100).map(f=>({
        id:f.id,name:f.name,mimeType:String(f.mimeType||''),
        modifiedTime:typeof f.modifiedTime==='string'?f.modifiedTime:null,
        size:typeof f.size==='string'?f.size:null
      }));
    return {provider:'google_drive',folderId:data.folder_id,
      files,truncated:Boolean(result.nextPageToken),indexed:false};
  }
  async disconnect(subject){
    subject=validateSubject(subject);
    const stored=this.decrypt(subject);
    if(!stored)return {connected:false,revoked:false};
    delete this.records[digest(subject)];
    this.save(); // local credentials are always removed even when remote revocation is unavailable
    let revoked=false;
    try{
      const response=await this.fetch(GOOGLE_REVOKE,{
        method:'POST',
        headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:new URLSearchParams({token:stored.refresh_token}).toString(),
        signal:AbortSignal.timeout(8000)
      });
      revoked=response.ok;
    }catch{}
    return {connected:false,revoked,externalRevocationUnconfirmed:!revoked};
  }
}
