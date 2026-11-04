'use strict';
let auth='',state=null,pending=null,permissions=[];
const byId=id=>document.getElementById(id);
async function api(route,body={}){
  const response=await fetch('/api/'+route,{method:'POST',headers:{'Content-Type':'application/json','Authorization':auth},body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok)throw Error(data.error||'Request failed');
  return data;
}
function message(text){byId('status').textContent=text;}
function preview(event,operation){
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
  byId('refresh').disabled=true;message('Loading authorized research history…');
  try{
    const [who,loaded,suggestions]=await Promise.all([api('status'),api('gardener/state'),api('gardener/proposals')]);
    permissions=who.scopes;byId('new-branch').hidden=!permissions.includes('write');state=loaded;byId('workspace').hidden=false;byId('history').textContent=JSON.stringify(state.events,null,2);render();
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
            elapsed_ms:Math.min(86400000,Math.round(performance.now()-started)),false_merge:check.checked});
            message('Review response recorded. This does not validate the claim.');feedback.replaceChildren();
          }catch(error){message(error.message);button.disabled=false;}
        });feedback.append(button);
      }
      article.append(feedback);list.append(article);
    }
    message('Workspace: '+who.tenant+' · '+Object.keys(state.branches).length+' branches · Research mode');
  }catch(error){message(error.message);}finally{byId('refresh').disabled=false;}
}
byId('connect').addEventListener('submit',event=>{event.preventDefault();state=null;byId('workspace').hidden=true;byId('branches').replaceChildren();byId('history').textContent='';auth='Bearer '+byId('token').value.trim();byId('token').value='';refresh();});
byId('refresh').addEventListener('click',refresh);
byId('search').addEventListener('input',()=>{if(state)render();});
byId('preview').addEventListener('close',async()=>{
  if(byId('preview').returnValue!=='apply'||!pending)return;
  message('Applying reviewed change…');
  try{await api('gardener/event',pending);await refresh();}catch(error){message(error.message);}finally{pending=null;}
});

byId('propose').addEventListener('submit',async event=>{
  event.preventDefault();
  const button=event.currentTarget.querySelector('button');
  button.disabled=true;message('Preserving the original source…');
  try{
    const file=byId('source-file').files[0];
    if(!file||file.size>250000)throw Error('Choose a source file up to 250 KB.');
    const bytes=new Uint8Array(await file.arrayBuffer());
    const encoded=btoa(Array.from(bytes,value=>String.fromCharCode(value)).join(''));
    const source=await api('source',{base64:encoded});
    await api('gardener/event',{event_id:'proposal-'+crypto.randomUUID(),operation:'PROPOSE',
      branch:byId('branch-name').value.trim(),source_sha256:source.source_sha256,source_ref:'file:'+file.name,
      statement:byId('statement').value.trim(),parents:[]});
    byId('propose').reset();byId('new-branch').open=false;await refresh();
  }catch(error){message(error.message);}finally{button.disabled=false;}
});
