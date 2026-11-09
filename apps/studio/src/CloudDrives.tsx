import React,{useEffect,useState} from 'react';

type Provider='google'|'microsoft'|'dropbox'|'box';
type Connection={id:string;provider:Provider;display_name:string;status:'connected'|'expired'|'error';scopes:string[];last_sync_at?:string;indexed_count?:number};
const providers:{id:Provider;name:string;scope:string}[]=[
 {id:'google',name:'Google Drive',scope:'drive.readonly'},
 {id:'microsoft',name:'OneDrive / SharePoint',scope:'Files.Read'},
 {id:'dropbox',name:'Dropbox',scope:'files.metadata.read / files.content.read'},
 {id:'box',name:'Box',scope:'Read files and folders'}
];
// Never put OAuth tokens in the browser or accept pasted API credentials.
// The backend owns OAuth state, PKCE, token encryption and the ingestion queue.
export default function CloudDrives({token}:{token:string}){
 const [connections,setConnections]=useState<Connection[]>([]);
 const [status,setStatus]=useState('Connect the registry and check which cloud providers are configured.');
 const [busy,setBusy]=useState(false);
 const [available,setAvailable]=useState(false);
 const [selected,setSelected]=useState('');
 async function api(path:string,init:RequestInit={}){
  const response=await fetch(path,{...init,headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json',...init.headers},cache:'no-store'});
  const result=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(result.error||('Cloud connector API unavailable (HTTP '+response.status+')'));
  return result;
 }
 async function refresh(){if(!token)return;setBusy(true);try{
  const result=await api('/v1/connectors');
  if(!Array.isArray(result.connections))throw new Error('Invalid connector response');
  setConnections(result.connections);setAvailable(true);setStatus('Connection inventory loaded.');
 }catch(e){setAvailable(false);setConnections([]);setStatus(String(e))}finally{setBusy(false)}}
 useEffect(()=>{setConnections([]);setAvailable(false);setStatus('Connect the registry and check which cloud providers are configured.')},[token]);
 async function connect(provider:Provider){setBusy(true);try{
  const r=await api('/v1/connectors/'+provider+'/authorize',{method:'POST',body:'{}'});
  // Backend must return a verified provider OAuth authorization URL, never a token.
  const url=new URL(r.authorization_url);
  if(url.protocol!=='https:'||!r.state_issued)throw new Error('OAuth initiation response invalid');
  const allowed:{[K in Provider]:string[]}={google:['accounts.google.com'],microsoft:['login.microsoftonline.com'],dropbox:['www.dropbox.com'],box:['account.box.com']};
  if(!allowed[provider].includes(url.hostname))throw new Error('Unexpected OAuth authorization host');
  window.location.assign(url.toString());
 }catch(e){setStatus(String(e));setBusy(false)}}
 async function sync(id:string){setBusy(true);try{await api('/v1/connectors/'+encodeURIComponent(id)+'/sync',{method:'POST',body:'{}'});setStatus('Sync queued; refresh to inspect progress.');await refresh()}catch(e){setStatus(String(e))}finally{setBusy(false)}}
 async function disconnect(id:string){if(!window.confirm('Disconnect this drive and revoke access? Indexed copies may require a separate retention-policy purge.'))return;
 setBusy(true);try{await api('/v1/connectors/'+encodeURIComponent(id),{method:'DELETE'});await refresh()}catch(e){setStatus(String(e))}finally{setBusy(false)}}
 return <section className="panel" aria-label="Cloud drive integrations">
  <h2>6. Cloud drives · Evidence sources</h2>
  <p>Connect cloud storage using provider OAuth with least-privilege read access. Source permissions, revisions, provenance and deletion handling must be enforced by the ingestion service before documents enter the Semantic Garden.</p>
  <button disabled={!token||busy} onClick={refresh}>Check integrations</button>
  <p className="status" role="status">{status}</p>
  {!available&&<p><strong>Not configured.</strong> The Studio UI does not itself authorize Google Drive or read cloud files. A registry connector API and secure OAuth backend must be deployed before these controls are enabled.</p>}
  <div className="columns">{providers.map(p=><div className="panel" key={p.id}>
   <h3>{p.name}</h3><p>Requested read-only scope: <code>{p.scope}</code></p>
   <button disabled={!token||!available||busy} onClick={()=>connect(p.id)}>Connect {p.name}</button>
  </div>)}</div>
  <h3>Connected sources</h3>
  {connections.length===0?<p>No cloud drives connected.</p>:<ul>{connections.map(c=><li key={c.id}>
   <strong>{c.display_name}</strong> · {c.provider} · {c.status} · Indexed: {c.indexed_count??'unknown'} · Last sync: {c.last_sync_at||'never'}
   <button disabled={busy||c.status!=='connected'} onClick={()=>sync(c.id)}>Sync</button>
   <button disabled={busy} onClick={()=>disconnect(c.id)}>Disconnect</button>
  </li>)}</ul>}
  <label>Source ID to inspect<input value={selected} onChange={e=>setSelected(e.target.value)} placeholder="Provider-qualified source ID (read-only)"/></label>
  <p>Cloud source search will become available after the connector API indexes permitted content with ACL-aware source anchors. No credentials are stored in browser local storage.</p>
 </section>;
}
