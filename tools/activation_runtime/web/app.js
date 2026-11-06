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
    permissions=who.scopes;byId('new-branch').hidden=!permissions.includes('write');byId('transformation-panel').hidden=!permissions.includes('write');byId('transform-form').hidden=!who.reviewed_activation_configured;byId('transform-availability').hidden=Boolean(who.reviewed_activation_configured);byId('observation-source').disabled=!permissions.includes('write');state=loaded;byId('workspace').hidden=false;byId('history').textContent=JSON.stringify(state.events,null,2);render();gardenUpdate();
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
    window.dispatchEvent(new CustomEvent('qr:ready',{detail:{who,state,suggestions}}));
  }catch(error){if(epoch===sessionEpoch)message(error.message);}finally{byId('refresh').disabled=false;}
}
byId('connect').addEventListener('submit',event=>{
  event.preventDefault();sessionEpoch++;state=null;pending=null;permissions=[];clearResults();gardenReset();if(typeof governanceReset==='function')governanceReset();if(typeof protReset==='function')protReset();if(typeof engineReset==='function')engineReset();
  if(byId('preview').open)byId('preview').close('cancel');
  for(const id of ['propose','transform-form','observation-form','validate-form','fallback-form'])byId(id).reset();
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


// ---- Semantic Gardener research tree -------------------------------------------------
const garden={time:0,atHead:true,selected:null,matches:null,fresh:new Set(),form:null};
function gardenReset(){garden.time=0;garden.atHead=true;garden.selected=null;garden.matches=null;garden.fresh=new Set();garden.form=null;
  byId('garden-svg').replaceChildren();byId('garden-feed').replaceChildren();byId('garden-result').textContent='';
  byId('garden-inspector').replaceChildren(textEl('p','Select a branch to inspect its history.','obs-empty'));}
function textEl(tag,text,cls){const node=document.createElement(tag);node.textContent=text;if(cls)node.className=cls;return node;}
function firstEvent(name){return state.events[state.branches[name].events[0]];}
function gardenUpdate(){
  if(!state)return;
  const head=state.head_sequence||0,slider=byId('garden-time');
  slider.max=String(head);
  if(garden.atHead||garden.time>head)garden.time=head;
  slider.value=String(garden.time);
  const at=state.order&&state.order[garden.time-1]?state.events[state.order[garden.time-1]]:null;
  byId('garden-time-label').textContent=head?('event '+garden.time+' / '+head+(at?' · '+at.operation+' '+at.branch:'')):'No events yet';
  const scene=Garden.render(byId('garden-svg'),state,garden.time,{selected:garden.selected,matches:garden.matches,fresh:garden.fresh,
    onSelect:name=>{garden.selected=name;garden.form=null;gardenUpdate();}});
  const canvas=byId('garden-svg').parentElement;
  if(canvas.scrollWidth>canvas.clientWidth){  // narrow screens: keep the selected branch (or the trunk) in view
    const focus=scene.pos[garden.selected]||{x:Garden.VIEW.w/2};
    canvas.scrollLeft=Math.max(0,focus.x/Garden.VIEW.w*canvas.scrollWidth-canvas.clientWidth/2);
  }
  garden.fresh=new Set();
  gardenInspector();gardenFeed();
}
function gardenFeed(){
  const list=byId('garden-feed');list.replaceChildren();
  for(const id of (state.order||[]).slice(-15).reverse()){
    const e=state.events[id],item=document.createElement('li');
    item.append(textEl('span',e.operation,'obs-op op-'+e.operation),document.createTextNode(' #'+e.sequence+' '+e.branch+' — '+e.statement+' · '+e.actor));
    list.append(item);
  }
}
function gardenInspector(){
  const box=byId('garden-inspector');box.replaceChildren();
  const name=garden.selected;
  if(!name||!state.branches[name]){box.append(textEl('p','Select a branch to inspect its history.','obs-empty'));return;}
  const view=Garden.computeAt(state,garden.time)[name],branch=state.branches[name],first=firstEvent(name);
  if(!view.visible){box.append(textEl('p',name+' does not exist yet at this point in history.','obs-empty'));return;}
  box.append(textEl('p','branch · '+name,'obs-meta'),textEl('h3',first.statement));
  const chips=document.createElement('div');chips.className='obs-chips';
  chips.append(textEl('span',view.active?(view.reopened?'Reopened':'Active'):'Pruned','obs-chip'),textEl('span','ledger: '+branch.evidence_status,'obs-chip'));
  if(view.open)chips.append(textEl('span','open challenge','obs-chip'));
  if(branch.parents.length>1)chips.append(textEl('span','synthesis · never inherits validation','obs-chip'));
  box.append(chips);
  box.append(textEl('p','source '+first.source_ref+' · '+first.source_sha256.slice(0,12)+'…','obs-meta'),
    textEl('p','parents: '+(branch.parents.join(', ')||'— root'),'obs-meta'));
  if(branch.reopened_context&&view.reopened)box.append(textEl('p','Reopened with context: pruned by '+(branch.reopened_context.pruned_by||'—')+'; prior challenges '+(branch.reopened_context.prior_challenges.join(', ')||'none'),'obs-meta'));
  const events=document.createElement('ol');events.className='obs-events';
  for(const e of view.events){const item=document.createElement('li');item.append(textEl('span',e.operation,'obs-op op-'+e.operation),textEl('span','#'+e.sequence+' '+e.statement));events.append(item);}
  box.append(events);
  const actions=document.createElement('div');actions.className='obs-actions';
  const canWrite=permissions.includes('write'),canReview=permissions.includes('review'),live=garden.time===(state.head_sequence||0);
  const add=(label,cls,handler,enabled)=>{const button=textEl('button',label,cls);button.type='button';button.disabled=!enabled;button.addEventListener('click',handler);actions.append(button);};
  add('Challenge','warn',()=>{garden.form='CHALLENGE';gardenInspector();},canWrite&&live&&view.active);
  add('Test with evidence','',()=>{garden.form='TEST';gardenInspector();},canWrite&&live&&view.active);
  add('Fork','ghost',()=>{garden.form='FORK';gardenInspector();},canWrite&&live&&view.active);
  add(branch.active?'Prune…':'Reopen…','ghost',()=>preview(state.events[branch.events.at(-1)],branch.active?'PRUNE':'REOPEN'),canReview&&live);
  box.append(actions);
  if(!live)box.append(textEl('p','Replaying history: return to the latest event to act.','obs-empty'));
  else if(!canWrite)box.append(textEl('p','Your access is read-only.','obs-empty'));
  if(garden.form)box.append(gardenForm(name,first));
}
function gardenForm(name,first){
  const form=document.createElement('form');form.className='obs-form';
  const kind=garden.form,ids={statement:'garden-statement',child:'garden-child',evidence:'garden-evidence'};
  const field=(label,id,input)=>{const l=textEl('label',label);l.htmlFor=id;input.id=id;form.append(l,input);};
  if(kind==='FORK'){const child=document.createElement('input');child.required=true;child.maxLength=100;child.pattern='[A-Za-z0-9][A-Za-z0-9._-]*';field('New branch name',ids.child,child);}
  const text=document.createElement('textarea');text.required=true;text.maxLength=2000;
  field(kind==='CHALLENGE'?'Counterexample or objection':(kind==='TEST'?'What the evidence shows':'Hypothesis'),ids.statement,text);
  if(kind==='TEST'){const ev=document.createElement('input');ev.required=true;ev.placeholder='evidence IDs recorded in the ledger, comma separated';field('Ledger evidence IDs',ids.evidence,ev);}
  form.append(textEl('p','Uses the branch source '+first.source_ref+'. Every action appends an event; nothing is deleted.','obs-empty'));
  const row=document.createElement('div');row.className='obs-actions';
  const submit=textEl('button',kind==='FORK'?'Create branch':'Append '+kind);submit.type='submit';
  const cancel=textEl('button','Cancel','ghost');cancel.type='button';cancel.addEventListener('click',()=>{garden.form=null;gardenInspector();});
  row.append(submit,cancel);form.append(row);
  form.addEventListener('submit',async ev=>{
    ev.preventDefault();const epoch=sessionEpoch;submit.disabled=true;
    const body={event_id:'ui-'+crypto.randomUUID(),operation:kind==='FORK'?'PROPOSE':kind,branch:kind==='FORK'?byId(ids.child).value.trim():name,
      source_sha256:first.source_sha256,source_ref:first.source_ref,statement:byId(ids.statement).value.trim(),parents:kind==='FORK'?[name]:[]};
    if(kind==='TEST')body.evidence_ids=byId(ids.evidence).value.split(',').map(v=>v.trim()).filter(Boolean);
    try{await api('gardener/event',body,epoch);if(kind==='FORK')garden.selected=body.branch;garden.form=null;garden.atHead=true;await refresh();message('Event appended. It does not validate the claim.');}
    catch(error){if(epoch===sessionEpoch)message(error.message);submit.disabled=false;}
  });
  return form;
}
byId('garden-time').addEventListener('input',event=>{if(!state)return;garden.time=Number(event.target.value);garden.atHead=garden.time===(state.head_sequence||0);garden.form=null;gardenUpdate();});
byId('garden-query').addEventListener('submit',async event=>{
  event.preventDefault();if(!state)return;const epoch=sessionEpoch;
  const text=byId('garden-text').value.trim(),filter=byId('garden-filter').value,body={limit:500};
  if(text)body.text=text;
  if(filter==='active')body.active=true;if(filter==='open')body.open_challenge=true;
  if(filter==='tested')body.evidence_status='TESTED';if(filter==='unverified')body.evidence_status='UNVERIFIED';
  if(!text&&filter==='all'){garden.matches=null;byId('garden-result').textContent='';gardenUpdate();return;}
  try{const result=await api('gardener/query',body,epoch);garden.matches=result.branches.map(b=>b.branch);
    byId('garden-result').textContent=result.total+' matching branch'+(result.total===1?'':'es')+' highlighted. Matches are structural, not validated.';gardenUpdate();}
  catch(error){if(epoch===sessionEpoch)byId('garden-result').textContent=error.message;}
});
setInterval(async()=>{
  if(!state||!auth||!byId('garden-live').checked||document.hidden)return;
  const epoch=sessionEpoch,before=new Set(Object.keys(state.branches));
  try{
    const delta=await api('gardener/query',{since:state.head_sequence||0,limit:1},epoch);
    if(!delta.events.length)return;
    const loaded=await api('gardener/state',{},epoch);ensureSession(epoch);
    state=loaded;garden.fresh=new Set(Object.keys(state.branches).filter(n=>!before.has(n)));
    byId('garden-result').textContent=delta.events.length+' new event'+(delta.events.length===1?'':'s')+' · latest '+delta.events.at(-1).operation+' on '+delta.events.at(-1).branch;
    render();gardenUpdate();
  }catch(_error){/* transient polling failures are ignored; the next tick retries */}
},4000);
let gardenResize=null;
window.addEventListener('resize',()=>{clearTimeout(gardenResize);gardenResize=setTimeout(()=>{if(state)gardenUpdate();},150);});
