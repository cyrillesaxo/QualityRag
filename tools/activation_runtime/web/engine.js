'use strict';
// Connects the console to the rest of the machinery: a live Engine panel on Home, the
// Evolution screen (gardener/evolution), schema validation (validate), original-byte
// retrieval (fallback) and branch deep links (#/tree/<branch>). Uses api(), byId(), textEl(),
// govEl() and sessionEpoch from app.js and governance.js. DOM APIs only.
const engine={};
function engineReset(){
  Object.assign(engine,{who:null,state:null,suggestions:null,health:null,evo:null,gate:null});
  byId('engine').replaceChildren(textEl('li','Loading…','hint'));
  for(const id of ['evo-summary','evo-champions','evo-cycles'])byId(id).replaceChildren();
  byId('evo-command').textContent='';byId('badge-evolution').hidden=true;
  byId('validate-result').textContent='';byId('validate-result').className='validate-result';byId('fallback-result').textContent='';
}
engineReset();
function short(sha){return sha?sha.slice(0,12)+'…':'—';}
function branchLink(name){const a=textEl('a',name,'mono');a.href='#/tree/'+encodeURIComponent(name);return a;}
function chip(text,tone){return textEl('span',text,'engine-chip '+tone);}

// ---------- Engine panel ----------
function engineRow(name,detail,state,tone,href){
  const link=textEl('a','Open');link.href=href;link.className='engine-open';link.setAttribute('aria-label','Open '+name);
  return govEl('li','engine-row',textEl('span','','engine-dot '+tone),
    govEl('span','engine-main',textEl('span',name,'engine-name'),textEl('span',detail,'engine-detail')),chip(state,tone),link);
}
function renderEngine(){
  const list=byId('engine');if(!engine.who){return;}
  const rows=[],st=engine.state,branches=st?Object.values(st.branches):[];
  rows.push(engine.gate===false?engineRow('Evidence gate','The policy routes did not answer.','Unavailable','bad','#/ask')
    :engineRow('Evidence gate','v0.1 deterministic gate: requirement links, distinct origins, age, scope, authority.',engine.gate?'Ready':'Checking…',engine.gate?'ok':'muted','#/ask'));
  rows.push(engineRow('Research tree',st?branches.length+' branch'+(branches.length===1?'':'es')+' · '+(st.head_sequence||0)+' events, append-only':'Loading…','Ready','ok','#/tree'));
  const counts={};for(const b of branches)counts[b.evidence_status]=(counts[b.evidence_status]||0)+1;
  const ledger=Object.entries(counts).map(([k,v])=>v+' '+k.toLowerCase()).join(' · ')||'No claims yet';
  rows.push(engineRow('Research ledger',ledger,'Ready','ok','#/review'));
  const n=engine.suggestions?(engine.suggestions.proposals||[]).length:0;
  rows.push(engineRow('Review queue',n?n+' suggestion'+(n===1?'':'s')+' waiting for a person':'Nothing waiting',n?'Waiting':'Clear',n?'warn':'ok','#/review'));
  if(engine.health){
    const ids=engine.health.findings.map(f=>f.id);
    const bad=ids.includes('trust.no-active-reviewer')||ids.includes('trust.unreadable');
    rows.push(engineRow('Reviewer trust',bad?'No active reviewer key: signed completion receipts cannot verify.':'Active reviewer keys loaded.',bad?'Needs setup':'Ready',bad?'bad':'ok','#/health'));
  }else rows.push(engineRow('Reviewer trust','Checking…','Checking…','muted','#/health'));
  const e=engine.evo;
  if(!e)rows.push(engineRow('Evolution','Checking…','Checking…','muted','#/evolution'));
  else if(e.status==='NOT_STARTED')rows.push(engineRow('Evolution','No cycle has run in this workspace yet. Cycles run on the host.','Not started','muted','#/evolution'));
  else rows.push(engineRow('Evolution',e.cycles.length+' recent cycle'+(e.cycles.length===1?'':'s')+' · '+e.champions.length+' champion'+(e.champions.length===1?'':'s')+' · '+e.budget.reserved_units+' of '+e.budget.limit_units+' work units used','Recorded','ok','#/evolution'));
  rows.push(engine.who.reviewed_activation_configured?engineRow('Reviewed activation','Signed transformations can run for this workspace.','Ready','ok','#/advanced')
    :engineRow('Reviewed activation','Reviewer authority is not configured for this workspace.','Not configured','muted','#/advanced'));
  rows.push(engineRow('Your access',engine.who.principal+' · '+engine.who.scopes.join(', ')+' · '+engine.who.mode.toLowerCase()+' mode','Signed in','ok','#/connect'));
  list.replaceChildren(...rows);
}
window.addEventListener('qr:ready',async e=>{
  Object.assign(engine,{who:e.detail.who,state:e.detail.state,suggestions:e.detail.suggestions});
  renderEngine();
  const epoch=sessionEpoch;
  try{await api('policy/example',{},epoch);engine.gate=true;}catch(_e){if(epoch===sessionEpoch)engine.gate=false;}
  if(epoch!==sessionEpoch)return;
  renderEngine();engineEvolution(true);
});
window.addEventListener('qr:health',e=>{engine.health=e.detail;renderEngine();});

// ---------- Evolution ----------
const STAGE_TONE={DONE:'ok'};
async function engineEvolution(silent){
  const epoch=sessionEpoch;
  try{
    const r=await api('gardener/evolution',{},epoch);
    engine.evo=r;renderEvolution();renderEngine();
  }catch(error){if(epoch===sessionEpoch&&!silent)govStatus(error.message);}
}
function renderEvolution(){
  const r=engine.evo;if(!r)return;
  const started=r.status!=='NOT_STARTED';
  const cycles=r.cycles||[],champions=r.champions||[],budget=r.budget||{limit_units:0,reserved_units:0};
  const open=cycles.filter(c=>c.stage!=='DONE').length;
  byId('badge-evolution').textContent=String(open);byId('badge-evolution').hidden=!open;
  byId('evo-summary').replaceChildren(
    govStat(started?'Recorded':'Not started','research state',started?'ok':''),
    govStat(cycles.length+(cycles.length===20?'+':''),'cycles recorded'),
    govStat(open,'in progress',open?'warn':''),
    govStat(champions.length,'champions'),
    govStat(started?budget.reserved_units+' / '+budget.limit_units:'—','work units used'));
  const champ=byId('evo-champions');champ.replaceChildren();
  if(!champions.length)champ.append(textEl('p',started?'No program has beaten its baseline yet.':'No champions yet. Run a cycle on the host to start.','hint'));
  else{
    const table=govEl('table','gov-table'),heads=['Purpose contract','Branch','Program'];
    table.append(govEl('thead','',govEl('tr','',...heads.map(h=>textEl('th',h)))));
    const tb=govEl('tbody','');
    for(const c of champions){const cells=[textEl('td',short(c.packspec_sha256),'mono'),govEl('td','',branchLink(c.branch)),textEl('td',short(c.program_sha256),'mono')];
      cells.forEach((x,i)=>x.dataset.label=heads[i]);tb.append(govEl('tr','',...cells));}
    table.append(tb);champ.append(govEl('div','table-wrap',table));
  }
  const cyc=byId('evo-cycles');cyc.replaceChildren();
  if(!cycles.length)cyc.append(textEl('p','No cycles recorded.','hint'));
  else{
    const list=govEl('ul','evo-cycles');
    for(const c of cycles)list.append(govEl('li','',textEl('span','Cycle '+c.cycle,'mono'),chip(c.stage.toLowerCase().replaceAll('_',' '),STAGE_TONE[c.stage]||'warn')));
    cyc.append(list);
  }
  const tenant=engine.who?engine.who.tenant:'<tenant>';
  byId('evo-command').textContent='# On the host that owns the model and the sources:\npython -m tools.activation_runtime.evolution \\\n  --garden <service-root>/gardens/'+tenant+'/events.sqlite \\\n  --config research.json --model <ollama-model> --work-limit 200 --continuous\n\n# Status, from the same host:\npython -m tools.activation_runtime.evolution --garden <service-root>/gardens/'+tenant+'/events.sqlite --status';
}
byId('evo-refresh').addEventListener('click',()=>engineEvolution(false).then(()=>govStatus('Evolution status refreshed.')));
setInterval(()=>{if(engine.who&&!document.hidden&&/^#\/evolution/.test(location.hash))engineEvolution(true);},10000);

// ---------- Advanced: validate and fallback ----------
byId('validate-form').addEventListener('submit',async event=>{
  event.preventDefault();const epoch=sessionEpoch,out=byId('validate-result'),schema=byId('validate-schema').value;
  out.className='validate-result';out.textContent='Validating…';
  try{
    const value=await govFile(byId('validate-file'),'Document');
    if(value===null)throw Error('Choose a JSON document.');
    const r=await api('validate',{schema,value},epoch);
    out.className='validate-result ok';out.textContent='Valid '+schema+' document. Its meaning is not admitted ('+r.semantic_admission.toLowerCase()+').';
  }catch(error){if(epoch===sessionEpoch){out.className='validate-result bad';
    out.textContent=error.message==='INVALID_OR_UNAVAILABLE_INPUT'?'Not a valid '+schema+' document. The server does not echo details; validate locally with the schema in tools/activation_runtime/schemas for the exact error.':error.message;}}
});
byId('fallback-form').addEventListener('submit',async event=>{
  event.preventDefault();const epoch=sessionEpoch,out=byId('fallback-result'),sha=byId('fallback-hash').value.trim();
  out.textContent='Fetching…';
  try{
    const r=await api('fallback',{source_sha256:sha},epoch);
    const bytes=Uint8Array.from(atob(r.base64),c=>c.charCodeAt(0));
    const url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'}));
    const a=document.createElement('a');a.href=url;a.download='source-'+sha.slice(0,12);a.click();
    setTimeout(()=>URL.revokeObjectURL(url),10000);
    let check='Integrity not checked: this browser has no Web Crypto here.';
    if(window.crypto&&crypto.subtle){
      const hex=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
      check=hex===sha?'SHA-256 verified in this browser.':'Warning: the bytes do not match the requested SHA-256.';
    }
    out.textContent='Downloaded '+bytes.length+' original bytes. '+check;
  }catch(error){if(epoch===sessionEpoch)out.textContent=error.message==='INVALID_OR_UNAVAILABLE_INPUT'?'No source with that SHA-256 in this workspace.':error.message;}
});

// ---------- Screen entry: Evolution refresh and branch deep links ----------
function engineEnter(view,hash){
  if(view==='evolution')engineEvolution(true);
  if(view==='tree'){
    const m=/^#\/tree\/(.+)$/.exec(hash||'');
    if(m&&typeof state!=='undefined'&&state){
      const name=decodeURIComponent(m[1]);
      if(state.branches[name]){garden.selected=name;garden.form=null;gardenUpdate();}
      else govStatus('No branch named '+name+' in this workspace.');
    }
  }
}
