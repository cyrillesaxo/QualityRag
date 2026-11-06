'use strict';
// Protected data & release (ADR-0002). Uses api(), byId(), textEl(), govEl() and sessionEpoch.
// DOM APIs only (CSP: no inline styles, no innerHTML). The browser never sees a protected value
// unless the gateway released it in clear to a destination whose contract allows that.
const prot={status:null,docs:[],admission:null};
const REASON_WORD={
  UNREGISTERED_DESTINATION:'This destination has no published contract.',
  USER_NOT_ENTITLED:'Your token is not entitled to send here for this purpose and operation.',
  LABEL_TAMPERED:'The evidence label was changed after admission.',
  LABEL_FROM_ANOTHER_PRINCIPAL:'The evidence label belongs to another user or tenant.',
  CROSS_TENANT:'The destination belongs to another tenant.',
  DESTINATION_DOES_NOT_ACCEPT_OPERATION:'The destination does not accept this operation.',
  PLAINTEXT_SENSITIVE_DATA:'The text contains a card number in clear.',
  OUTPUT_TOO_LARGE:'The text is larger than the destination allows.',
  TOKEN_NOT_IN_MODEL_CONTEXT:'The text names a protected value the model was never given.',
  INDEPENDENT_REVIEW_REQUIRED:'This release needs a signed review by someone else.',
  REVIEW_REJECTED_OR_STALE:'The review does not match this exact text, destination, purpose and operation, or was signed by the requester.'};
const NORMAL_WORD={IMAGE_REMOVED:'images removed',LINK_REMOVED:'links to unlisted sites removed',
  URL_REMOVED:'addresses to unlisted sites removed',INVISIBLE_CHARACTERS_REMOVED:'invisible characters removed'};
const TOKEN_RE=/\[[A-Z][A-Z0-9_]{1,31}:tok_[0-9a-f]{16}\]/g;

function protReason(r){
  if(r.startsWith('SOURCE_RELEASE_REFUSED:'))return 'The source '+r.split(':')[1]+' does not release to this destination for this purpose and operation.';
  if(r.startsWith('DESTINATION_DOES_NOT_ACCEPT:'))return 'The destination does not accept data from '+r.split(':')[1]+'.';
  return REASON_WORD[r]||r;
}
function protText(text){
  // Show protected references as tags, never as values.
  const out=document.createElement('p');out.className='prot-text';let last=0;
  for(const m of text.matchAll(TOKEN_RE)){
    if(m.index>last)out.append(document.createTextNode(text.slice(last,m.index)));
    out.append(govTag(m[0].slice(1,m[0].indexOf(':'))+' · protected','prot-token'));last=m.index+m[0].length;
  }
  if(last<text.length)out.append(document.createTextNode(text.slice(last)));
  return out;
}
function protReset(){
  Object.assign(prot,{status:null,docs:[],admission:null});
  for(const id of ['prot-contracts','prot-docs','prot-admit-result','prot-release-result','prot-receipts'])byId(id).replaceChildren();
  byId('prot-unconfigured').hidden=true;byId('prot-configured').hidden=true;
}
function protList(items){return items.length?items.map(x=>x).join(', '):'none';}
function protContracts(contracts){
  const box=byId('prot-contracts');box.replaceChildren();
  if(!contracts.length){box.append(textEl('p','No published contracts for this tenant.','hint'));return;}
  for(const c of contracts){
    const card=govEl('div','card glass prot-card',textEl('span',c.kind==='source'?'Source':'Destination','card-kicker'),textEl('strong',c.id));
    if(c.kind==='source'){
      card.append(textEl('p','Visible as-is: '+protList(c.fields.public)),
        textEl('p','Protected (tokens): '+protList(c.fields.sensitive.map(f=>f.field+' → '+f.class))),
        textEl('p','Free text: '+(c.text==='OWNER_CLASSIFIED'?'classified by the owner':'unclassified, quarantined')),
        textEl('p','Releases to: '+protList(c.release.map(r=>r.destination+' ('+r.operations.join('/')+')'))),
        textEl('p','Shown in clear only to: '+protList(c.detokenize.map(r=>r.class+' → '+r.destination))));
    }else{
      card.append(textEl('p','Accepts: '+protList(c.accepts.sources)+' · operations '+protList(c.accepts.operations)),
        textEl('p','In clear: '+protList(c.accepts.classes)),
        textEl('p','Links allowed to: '+protList(c.link_hosts)),
        textEl('p','Signed review: '+(c.requires_review?'always':c.review_classes.length?'when releasing '+c.review_classes.join(', '):'not required')));
    }
    box.append(card);
  }
}
function protDocs(){
  const box=byId('prot-docs');box.replaceChildren();
  if(!prot.docs.length){box.append(textEl('p','No protected documents yet. Ingest a document signed by its owning resource (protect/ingest).','hint'));return;}
  for(const d of prot.docs){
    const head=govEl('div','prot-doc-head',textEl('strong',d.id),govTag(d.origin),textEl('span','observed '+d.observed_at,'hint'));
    if(d.quarantine.length)head.append(govTag('quarantined: '+d.quarantine.map(q=>q.reason.toLowerCase().replace(/_/g,' ')).join(', '),'bad'));
    const item=govEl('div','prot-doc',head);
    const attrs=Object.entries(d.safe_attributes||{}).map(([k,v])=>k+': '+Object.values(v).join(' ')).join(' · ');
    if(attrs)item.append(textEl('p','Approved attributes: '+attrs,'hint'));
    for(const c of d.chunks){
      const id='prot-chunk-'+c.id;
      const box2=document.createElement('input');box2.type='checkbox';box2.id=id;box2.value=c.id;box2.checked=!d.quarantine.length&&!!c.requirement_id;box2.disabled=!!d.quarantine.length;
      const label=document.createElement('label');label.htmlFor=id;label.className='prot-chunk';
      label.append(box2,govEl('span','',textEl('span',c.id+(c.requirement_id?' · '+human(c.requirement_id):''),'mono hint'),protText(c.text)));
      item.append(label);
    }
    box.append(item);
  }
}
function protReceipts(receipts){
  const box=byId('prot-receipts');box.replaceChildren();
  if(!receipts.length){box.append(textEl('p','No releases yet.','hint'));return;}
  const table=document.createElement('table');table.className='observation-table';
  const head=document.createElement('tr');for(const h of ['When','Decision','Destination','Purpose · operation','Who','Why','In clear'])head.append(textEl('th',h));
  table.append(govEl('thead','',head));const body=document.createElement('tbody');
  for(const r of receipts){
    const row=document.createElement('tr');
    row.append(textEl('td',new Date(r.at).toLocaleString()),govEl('td','',govTag(r.decision==='RELEASE'?'Released':'Denied',r.decision==='RELEASE'?'ok':'bad')),
      textEl('td',r.destination),textEl('td',r.purpose+' · '+r.operation),textEl('td',r.principal||'—'),
      textEl('td',r.reasons.length?r.reasons.map(protReason).join(' '):(r.normalized.length?r.normalized.map(n=>NORMAL_WORD[n]||n).join(', '):'—')),
      textEl('td',r.detokenized.length?r.detokenized.map(d=>d.class).join(', '):'nothing'));
    body.append(row);
  }
  table.append(body);box.append(govEl('div','table-wrap',table),textEl('p','Receipts are hash-chained and hold hashes and classes, never protected values.','hint'));
}
async function protLoad(){
  const epoch=sessionEpoch;
  try{
    const st=await api('protect/status',{},epoch);
    prot.status=st;
    byId('prot-unconfigured').hidden=!!st.configured;byId('prot-configured').hidden=!st.configured;
    if(!st.configured)return;
    byId('prot-summary').textContent=st.contracts.length+' published contract'+(st.contracts.length===1?'':'s')+' · '+
      plural(st.documents,'protected document')+(st.quarantined?' · '+st.quarantined+' quarantined':'');
    protContracts(st.contracts);
    const dests=st.contracts.filter(c=>c.kind==='destination').map(c=>c.id);
    const sel=byId('prot-destination');sel.replaceChildren(...dests.map(d=>{const o=document.createElement('option');o.value=d;o.textContent=d;return o;}));
    const ent=(st.entitled||[]);
    const fill=()=>{const e=ent.find(x=>x.destination===sel.value);if(e){byId('prot-purpose').value=e.purposes[0];byId('prot-operation').value=e.operations[0];}};
    if(ent.length&&dests.includes(ent[0].destination))sel.value=ent[0].destination;
    sel.onchange=fill;fill();
    byId('prot-entitled').textContent=ent.length?'Your token may send: '+ent.map(e=>e.destination+' for '+e.purposes.join('/')+' · '+e.operations.join('/')).join('; '):'Your token has no outbound entitlements.';
    prot.docs=(await api('protect/documents',{},epoch)).documents;protDocs();
    protReceipts((await api('protect/receipts',{},epoch)).receipts);
  }catch(error){if(epoch===sessionEpoch)govStatus(error.message);}
}
byId('prot-admit-form').addEventListener('submit',async e=>{
  e.preventDefault();const epoch=sessionEpoch;
  const chosen=[...document.querySelectorAll('#prot-docs input[type=checkbox]:checked')].map(x=>x.value);
  const reqs=[...new Set(prot.docs.flatMap(d=>d.chunks).filter(c=>chosen.includes(c.id)&&c.requirement_id).map(c=>c.requirement_id))];
  const box=byId('prot-admit-result');box.replaceChildren();
  if(!chosen.length||!reqs.length){box.append(textEl('p','Choose at least one passage linked to a requirement.','hint'));return;}
  try{
    const pack={id:'console-protected-check',version:'1',requirements:reqs.map(id=>({id,min_independent_sources:1}))};
    const a=await api('protect/admit',{pack,retrieved:chosen},epoch);prot.admission=a;
    box.append(govEl('div','card glass',textEl('span','Admission','card-kicker'),
      textEl('strong',a.can_generate?'Supported: the model may answer from this evidence':'Not admitted: the model must not answer')));
    for(const r of a.refused)box.append(textEl('p',(r.document||r.chunk)+': '+r.reason.toLowerCase().replace(/_/g,' '),'hint'));
    if(a.context.length){
      box.append(textEl('h3','What the model sees'));
      for(const c of a.context)box.append(govEl('div','prot-context',textEl('span',c.chunk_id+' · untrusted source text','mono hint'),protText(c.text)));
      byId('prot-output').value=a.context.map(c=>c.text).join('\n');
    }
    byId('prot-label').textContent=a.label?'Label '+a.label.label_sha256.slice(0,12)+'… · sources '+a.label.sources.join(', ')+' · '+plural(a.label.tokens.length,'protected value'):'No label: nothing was admitted.';
  }catch(error){if(epoch===sessionEpoch)box.append(textEl('p',error.message,'hint'));}
});
byId('prot-release-form').addEventListener('submit',async e=>{
  e.preventDefault();const epoch=sessionEpoch;const box=byId('prot-release-result');box.replaceChildren();
  try{
    const r=await api('protect/release',{output:byId('prot-output').value,destination:byId('prot-destination').value,
      purpose:byId('prot-purpose').value.trim(),operation:byId('prot-operation').value.trim(),
      label:prot.admission?prot.admission.label:null},epoch);
    const card=govEl('div','card glass '+(r.decision==='RELEASE'?'prot-ok':'prot-bad'),textEl('span','Outbound gateway','card-kicker'),
      textEl('strong',r.decision==='RELEASE'?'Released':'Denied'));
    for(const reason of r.reasons)card.append(textEl('p',protReason(reason)));
    if(r.receipt.normalized.length)card.append(textEl('p','Cleaned before release: '+r.receipt.normalized.map(n=>NORMAL_WORD[n]||n).join(', ')+'.'));
    if(r.decision==='RELEASE'){
      card.append(textEl('p',r.receipt.detokenized.length?'Shown in clear because the owner\'s contract allows it: '+r.receipt.detokenized.map(d=>d.class).join(', ')+'.':'Protected values stay masked for this destination.'),
        textEl('pre',r.text,'gov-code'));
    }
    card.append(textEl('p','Receipt '+r.receipt.receipt_hash.slice(0,16)+'… recorded.','hint'));
    box.append(card);
    protReceipts((await api('protect/receipts',{},epoch)).receipts);
  }catch(error){if(epoch===sessionEpoch)box.append(textEl('p',error.message,'hint'));}
});
window.addEventListener('qr:ready',()=>{if(location.hash==='#/protect')protLoad();});
window.addEventListener('hashchange',()=>{if(location.hash==='#/protect')protLoad();});
protReset();
