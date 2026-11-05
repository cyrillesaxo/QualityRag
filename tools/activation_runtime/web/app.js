'use strict';
let auth='',state=null,pending=null,permissions=[],sessionEpoch=0,pendingEpoch=0,receipt=null;
const byId=id=>document.getElementById(id);
const rawReceipts=new Map();
function ensureSession(epoch){if(epoch!==sessionEpoch)throw Error('Workspace changed. Run the operation again.');}
function parseJson(text){return JSON.parse(text,(_key,value)=>{
  if(typeof value==='number'&&(!Number.isFinite(value)||(Number.isInteger(value)&&!Number.isSafeInteger(value))))throw Error('This browser cannot represent an integer exactly. Use the Python client.');
  return value;
});}
async function api(route,body={},epoch=sessionEpoch){
  ensureSession(epoch);
  const raw=typeof body==='string'?body:JSON.stringify(body);
  if(new TextEncoder().encode(raw).length>524288)throw Error('Request exceeds the workspace limit.');
  const response=await fetch('/api/'+route,{method:'POST',headers:{'Content-Type':'application/json','Authorization':auth},body:raw,redirect:'error',signal:AbortSignal.timeout(15000)});
  const text=await response.text();ensureSession(epoch);
  const data=parseJson(text);
  if(!response.ok)throw Error(data.error||'Request failed');
  if(['reviewed-run','observations'].includes(route))rawReceipts.set(route,text);
  return data;
}
function clearResults(){
  receipt=null;rawReceipts.clear();byId('transform-result').hidden=true;byId('observation-result').hidden=true;
  for(const id of ['transform-heading','transform-summary','transform-output','transform-receipt','observation-summary','observation-receipt','preview-text','preview-data'])byId(id).textContent='';
  byId('observation-nodes').replaceChildren();
}
function message(text){byId('status').textContent=text;}
function preview(event,operation){
  pendingEpoch=sessionEpoch;
  pending={event_id:'review-'+crypto.randomUUID(),operation,branch:event.branch,
    source_sha256:event.source_sha256,source_ref:event.source_ref,
    statement:operation+' reviewed in the workspace',parents:[]};
  byId('preview-text').textContent='This change is append-only. The prior branch and its evidence remain in history.';
  byId('preview-data').textContent=JSON.stringify(pending,null,2);
  byId('preview').showModal();
}
function render(){
  const tbody=byId('branches');tbody.replaceChildren();
  const term=byId('search').value.toLowerCase();
  const rows=Object.entries(state.branches).filter(([name,branch])=>(name+' '+branch.evidence_status).toLowerCase().includes(term));
  if(!rows.length){const row=tbody.insertRow();const cell=row.insertCell();cell.colSpan=5;cell.textContent='No matching branches. Add a source-linked branch to start a research history.';return;}
  for(const [name,branch] of rows){
    const row=tbody.insertRow();
    for(const text of [name,branch.active?'Active':'Pruned',branch.evidence_status,branch.events.length+' events'])row.insertCell().textContent=text;
    const button=document.createElement('button');button.type='button';button.textContent=branch.active?'Review pruning':'Review reopening';
    button.disabled=!permissions.includes('review');
    if(button.disabled)button.textContent='Review restricted';
    button.addEventListener('click',()=>preview(state.events[branch.events.at(-1)],branch.active?'PRUNE':'REOPEN'));
    row.insertCell().append(button);
  }
}
async function refresh(){
  const epoch=sessionEpoch;
  byId('refresh').disabled=true;message('Loading authorized research history…');
  try{
    const [who,loaded,suggestions]=await Promise.all([api('status',{},epoch),api('gardener/state',{},epoch),api('gardener/proposals',{},epoch)]);
    permissions=who.scopes;byId('new-branch').hidden=!permissions.includes('write');byId('transformation-panel').hidden=!permissions.includes('write');byId('transform-form').hidden=!who.reviewed_activation_configured;byId('transform-availability').hidden=Boolean(who.reviewed_activation_configured);byId('observation-source').disabled=!permissions.includes('write');state=loaded;byId('workspace').hidden=false;byId('history').textContent=JSON.stringify(state.events,null,2);render();
    const list=byId('proposals');list.replaceChildren();
    if(!suggestions.proposals.length)list.textContent='No suggestions in the current bounded scan.';
    for(const proposal of suggestions.proposals){
      const article=document.createElement('article');article.className='proposal';
      const title=document.createElement('h3');title.textContent=proposal.kind.replaceAll('_',' ');
      const text=document.createElement('p');text.textContent=proposal.branches.join(', ')+' · Confidence not yet calibrated';
      const details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');
      summary.textContent='Inspect source anchors';pre.textContent=JSON.stringify(proposal,null,2);details.append(summary,pre);article.append(title,text,details);
      const started=performance.now(),feedback=document.createElement('div');
      feedback.className='actions';
      const correction=document.createElement('label'),check=document.createElement('input');
      check.type='checkbox';correction.append(check,document.createTextNode(' A related change removed a valid branch'));
      article.append(correction);
      for(const [label,verdict,useful] of [['Useful','CONFIRMED',true],['Needs correction','INCORRECT',false]]){
        const button=document.createElement('button');button.type='button';button.textContent=label;
        button.addEventListener('click',async()=>{
          button.disabled=true;
          try{await api('gardener/outcome',{proposal_id:proposal.id,verdict,useful,
            elapsed_ms:Math.min(86400000,Math.round(performance.now()-started)),false_merge:check.checked},epoch);
            message('Review response recorded. This does not validate the claim.');feedback.replaceChildren();
          }catch(error){if(epoch===sessionEpoch)message(error.message);button.disabled=false;}
        });feedback.append(button);
      }
      article.append(feedback);list.append(article);
    }
    message('Workspace: '+who.tenant+' · '+Object.keys(state.branches).length+' branches · Research mode');
  }catch(error){if(epoch===sessionEpoch)message(error.message);}finally{byId('refresh').disabled=false;}
}
byId('connect').addEventListener('submit',event=>{
  event.preventDefault();sessionEpoch++;state=null;pending=null;permissions=[];clearResults();
  if(byId('preview').open)byId('preview').close('cancel');
  for(const id of ['propose','transform-form','observation-form'])byId(id).reset();
  byId('search').value='';byId('workspace').hidden=true;byId('branches').replaceChildren();byId('proposals').replaceChildren();byId('history').textContent='';
  auth='Bearer '+byId('token').value.trim();byId('token').value='';refresh();
});
byId('refresh').addEventListener('click',refresh);
byId('search').addEventListener('input',()=>{if(state)render();});
byId('preview').addEventListener('close',async()=>{
  if(byId('preview').returnValue!=='apply'||!pending)return;
  const event=pending,epoch=pendingEpoch;pending=null;
  message('Applying reviewed change…');
  try{await api('gardener/event',event,epoch);ensureSession(epoch);await refresh();}catch(error){if(epoch===sessionEpoch)message(error.message);}
});

byId('propose').addEventListener('submit',async event=>{
  event.preventDefault();
  const epoch=sessionEpoch,button=event.currentTarget.querySelector('button');
  button.disabled=true;message('Preserving the original source…');
  try{
    const file=byId('source-file').files[0];
    if(!file||file.size>250000)throw Error('Choose a source file up to 250 KB.');
    const bytes=new Uint8Array(await file.arrayBuffer());ensureSession(epoch);
    const encoded=btoa(Array.from(bytes,value=>String.fromCharCode(value)).join(''));
    const source=await api('source',{base64:encoded},epoch);
    await api('gardener/event',{event_id:'proposal-'+crypto.randomUUID(),operation:'PROPOSE',
      branch:byId('branch-name').value.trim(),source_sha256:source.source_sha256,source_ref:'file:'+file.name,
      statement:byId('statement').value.trim(),parents:[]},epoch);
    byId('propose').reset();byId('new-branch').open=false;await refresh();
  }catch(error){if(epoch===sessionEpoch)message(error.message);}finally{button.disabled=false;}
});


async function readFile(input,limit,epoch){
  const file=byId(input).files[0];
  if(!file||file.size<1||file.size>limit)throw Error('Choose a nonempty file within the displayed workflow limit.');
  const bytes=new Uint8Array(await file.arrayBuffer());ensureSession(epoch);return bytes;
}
async function readRequest(input,limit,epoch){
  const bytes=await readFile(input,limit,epoch);
  const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
  return {text,value:parseJson(text)};
}
function encoded(bytes){return btoa(Array.from(bytes,value=>String.fromCharCode(value)).join(''));}
byId('transform-form').addEventListener('submit',async event=>{
  event.preventDefault();const epoch=sessionEpoch,button=event.currentTarget.querySelector('button');button.disabled=true;
  receipt=null;rawReceipts.delete('reviewed-run');byId('transform-result').hidden=true;byId('transform-output').textContent='';byId('transform-receipt').textContent='';
  message('Checking the signed transformation…');
  try{
    const request=await readRequest('transform-request',350000,epoch);
    const source=await readFile('transform-source',65536,epoch);
    // Keep the original JSON number spelling for signature/canonical fidelity.
    const body='{"base64":'+JSON.stringify(encoded(source))+',"request":'+request.text+'}';
    const result=await api('reviewed-run',body,epoch);receipt=result;
    byId('transform-heading').textContent=result.action==='FALLBACK'?'Original restored after failed checks':(result.action==='REFUSE'?'Transformation refused':'Finite preservation checks passed');
    byId('transform-summary').textContent='Finite result: '+result.finite_constraint_result+' · Domain admission: '+result.qualityrag_admission;
    byId('transform-output').textContent=result.output===null?'No transformed output was released.':JSON.stringify(result.output,null,2);
    byId('transform-receipt').textContent=rawReceipts.get('reviewed-run');byId('transform-result').hidden=false;
    message('Transformation finished. No generation or new approval was authorized.');
  }catch(error){if(epoch===sessionEpoch)message(error.message);}finally{button.disabled=false;}
});
byId('download-receipt').addEventListener('click',()=>{
  if(!receipt)return;
  const url=URL.createObjectURL(new Blob([rawReceipts.get('reviewed-run')],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='qualityrag-transformation-receipt.json';link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
byId('observation-form').addEventListener('submit',async event=>{
  event.preventDefault();const epoch=sessionEpoch,button=event.currentTarget.querySelector('button');button.disabled=true;
  byId('observation-result').hidden=true;byId('observation-nodes').replaceChildren();byId('observation-receipt').textContent='';
  message('Checking source observations…');
  try{
    const request=(await readRequest('observation-request',250000,epoch)).value;
    if(!request||typeof request!=='object'||Array.isArray(request)||!Array.isArray(request.observations)||Object.keys(request).some(key=>!['observations','rename'].includes(key)))throw Error('Choose an observation draft request with supported options.');
    let source=byId('observation-hash').value.trim();const file=byId('observation-source').files[0];
    if(Boolean(source)===Boolean(file))throw Error('Choose exactly one source file or existing source hash.');
    if(file)source=(await api('source',{base64:encoded(await readFile('observation-source',65536,epoch))},epoch)).source_sha256;
    const result=await api('observations',{source_sha256:source,...request},epoch);
    const tbody=byId('observation-nodes');tbody.replaceChildren();
    for(const node of result.ast.nodes){
      const row=tbody.insertRow();
      const roles=Object.entries(node.roles).map(([role,target])=>role+': '+target).join(' · ');
      const annotation=[node.value===null?'Value not specified':String(node.value),roles,'Polarity: '+node.polarity,'Modality: '+node.modality,
        node.quantity===null?'':'Quantity: '+node.quantity+' '+node.unit,
        node.temporal_order.length?'After (ordered): '+node.temporal_order.join(' → '):''].filter(Boolean).join('\n');
      const values=[node.id,node.kind,annotation,node.source.quote];
      for(let i=0;i<values.length;i++){const cell=row.insertCell();cell.dataset.label=['ID','Kind','Annotation','Quoted source'][i];cell.textContent=values[i];}
    }
    byId('observation-summary').textContent=result.ast.nodes.length+' observations · '+result.ast.joins.length+' role references · Domain validity: '+result.domain_validity+(result.transition?' · ID transition checked':'');
    byId('observation-receipt').textContent=rawReceipts.get('observations');byId('observation-result').hidden=false;
    message('Structural checks passed. Annotation meaning remains unknown.');
  }catch(error){if(epoch===sessionEpoch)message(error.message);}finally{button.disabled=false;}
});
