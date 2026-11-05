'use strict';
// Evidence screens: Check an answer, Health, Policy changes, Alternatives. Uses api(), byId(),
// textEl() and sessionEpoch from app.js. DOM APIs only (CSP: no inline styles, no innerHTML).
// Every screen works on sample data by default; JSON stays under "Advanced".
const gov={};
const VERDICT_WORD={ADMIT:'Supported',INCONCLUSIVE:'Not enough evidence',REFUSE:'Contradicted'};
const SEVERITY_WORD={ERROR:'Must fix',WARN:'Review',INFO:'Good to know'};
const STATUS_WORD={SAT:'Works',UNSAT:'Fails',UNKNOWN:'Unknown'};

function governanceReset(){
  Object.assign(gov,{docs:null,example:null,usingSample:false,test:null,pack:null,selected:null,filter:'all',
    cases:null,ownCases:false,branchTouched:false,cands:null,sib:null,health:null,healthFor:null});
  for(const id of ['gov-test-result','gov-advise-result','gov-replay-result','gov-sib-result']){const n=byId(id);n.replaceChildren();n.hidden=true;}
  for(const id of ['gov-question','gov-pack','gov-retrieved','gov-branch','gov-sib-function','gov-sib-contracts'])byId(id).value='';
  byId('gov-passages').replaceChildren(textEl('p','Load documents to choose passages.','hint'));
  byId('gov-pack-editor').replaceChildren();byId('gov-branch-editor').replaceChildren();
  byId('gov-status').textContent='';byId('gov-docs-label').textContent='No documents loaded.';
  byId('gov-cases-label').textContent='No test cases loaded.';byId('gov-sib-label').textContent='No candidates loaded.';
  byId('gov-sample').hidden=true;byId('gov-own-docs').hidden=true;
}
function govEl(tag,cls,...children){const n=document.createElement(tag);if(cls)n.className=cls;for(const c of children)n.append(c);return n;}
function govStatus(text){byId('gov-status').textContent=text;}
function govJson(text,name){try{return JSON.parse(text);}catch(_e){throw Error(name+' is not valid JSON. Fix it under Advanced.');}}
async function govFile(input,name){
  const file=input.files[0];if(!file)return null;
  if(file.size>450000)throw Error(name+' exceeds 450 KB.');
  return govJson(await file.text(),name);
}
function govIds(text){return text.split(/[\s,]+/).map(s=>s.trim()).filter(Boolean);}
function pct(x){return x===null||x===undefined?'—':(x*100).toFixed(1)+'%';}
function plural(n,word,many){return n+' '+(n===1?word:(many||word+'s'));}
function human(id){return id.replace(/[-_]+/g,' ');}
function govStep(name){window.dispatchEvent(new CustomEvent('qr:step',{detail:name}));}
function govStat(value,label,tone){return govEl('div','gov-stat'+(tone?' '+tone:''),textEl('span',String(value),'gov-stat-value'),textEl('span',label,'gov-stat-label'));}
function govTag(text,cls){return textEl('span',text,'gov-tag mono'+(cls?' '+cls:''));}
governanceReset();

// ---------- Policy editor: friendly fields over the PackSpec JSON ----------
function packEditor(containerId,textareaId,onEdit){
  const box=byId(containerId);box.replaceChildren();
  let pack;
  try{pack=JSON.parse(byId(textareaId).value);}catch(_e){box.append(textEl('p','The policy JSON under Advanced is not valid.','hint warn'));return;}
  if(!pack||!Array.isArray(pack.requirements)){box.append(textEl('p','No policy loaded yet.','hint'));return;}
  box.append(textEl('p',(pack.id||'policy')+' · version '+(pack.version||'?'),'hint mono'));
  pack.requirements.forEach((r,i)=>{
    const n=containerId+'-'+i;
    const sources=document.createElement('input');sources.type='number';sources.min='1';sources.max='20';sources.id=n+'-src';
    sources.value=String(r.min_independent_sources||1);
    const age=document.createElement('input');age.type='number';age.min='1';age.id=n+'-age';age.placeholder='Any age';
    if(r.max_age_seconds)age.value=String(Math.round(r.max_age_seconds/86400));
    const write=()=>{
      const p=JSON.parse(byId(textareaId).value);const q=p.requirements[i];
      q.min_independent_sources=Math.max(1,Math.min(20,parseInt(sources.value,10)||1));
      const days=parseInt(age.value,10);if(days>0)q.max_age_seconds=days*86400;else delete q.max_age_seconds;
      byId(textareaId).value=JSON.stringify(p,null,2);if(onEdit)onEdit();
    };
    sources.addEventListener('input',write);age.addEventListener('input',write);
    const srcLabel=textEl('label','Independent sources');srcLabel.htmlFor=sources.id;
    const ageLabel=textEl('label','Max age (days)');ageLabel.htmlFor=age.id;
    sources.setAttribute('aria-label','Independent sources needed for '+human(r.id));
    age.setAttribute('aria-label','Maximum evidence age in days for '+human(r.id));
    box.append(govEl('div','req-row',textEl('span',human(r.id),'req-name'),
      govEl('div','req-field',srcLabel,sources),govEl('div','req-field',ageLabel,age)));
  });
}
byId('gov-pack').addEventListener('change',()=>packEditor('gov-pack-editor','gov-pack'));
byId('gov-branch').addEventListener('change',()=>{gov.branchTouched=true;packEditor('gov-branch-editor','gov-branch',()=>{gov.branchTouched=true;});});

// ---------- Passages checklist over the retrieved-IDs text ----------
function passageList(){
  const box=byId('gov-passages');box.replaceChildren();
  if(!gov.docs){box.append(textEl('p','Load documents to choose passages.','hint'));return;}
  const chosen=new Set(govIds(byId('gov-retrieved').value));let i=0;
  for(const doc of gov.docs)for(const chunk of doc.chunks||[]){
    const id='gov-p-'+(i++),input=document.createElement('input');
    input.type='checkbox';input.id=id;input.value=chunk.id;input.checked=chosen.has(chunk.id);
    input.addEventListener('change',()=>{
      const ids=[...box.querySelectorAll('input[type=checkbox]')].filter(x=>x.checked).map(x=>x.value);
      byId('gov-retrieved').value=ids.join(', ');
    });
    const text=chunk.text.length>160?chunk.text.slice(0,157)+'…':chunk.text;
    const label=govEl('label','passage',input,govEl('span','passage-body',
      govEl('span','passage-head',textEl('span',chunk.id,'mono'),textEl('span',[doc.origin,doc.format,doc.revision&&('rev '+doc.revision)].filter(Boolean).join(' · '),'hint')),
      textEl('span',text,'passage-text')));
    label.htmlFor=id;box.append(label);
  }
}
byId('gov-retrieved').addEventListener('change',passageList);

// ---------- Check an answer ----------
async function govLoadSample(){
  const ex=await api('policy/example',{},sessionEpoch);
  Object.assign(gov,{example:ex,docs:ex.documents,usingSample:true,cases:null,ownCases:false,branchTouched:false});
  byId('gov-question').value=ex.question;byId('gov-pack').value=JSON.stringify(ex.pack,null,2);
  byId('gov-retrieved').value=ex.retrieved.join(', ');
  const chunks=ex.documents.reduce((s,d)=>s+d.chunks.length,0);
  byId('gov-docs-label').textContent=ex.documents.length+' documents · '+chunks+' passages · from '+ex.source;
  byId('gov-sample-text').textContent='Using sample data: EU payments recovery, '+ex.documents.length+' documents with different sources and revisions.';
  byId('gov-sample').hidden=false;byId('gov-own-docs').hidden=true;
  packEditor('gov-pack-editor','gov-pack');passageList();
  return ex;
}
byId('gov-example').addEventListener('click',async()=>{
  try{await govLoadSample();govStatus('Sample data loaded. Choose Check answer.');}catch(error){govStatus(error.message);}
});
byId('gov-own').addEventListener('click',()=>{byId('gov-own-docs').hidden=false;byId('gov-docs').focus();});
byId('gov-docs').addEventListener('change',async()=>{
  try{const docs=await govFile(byId('gov-docs'),'Documents file');if(!Array.isArray(docs))throw Error('Documents file must be a JSON list.');
    gov.docs=docs;gov.usingSample=false;gov.cases=null;gov.branchTouched=false;byId('gov-sample').hidden=true;
    byId('gov-docs-label').textContent=docs.length+' documents loaded from '+byId('gov-docs').files[0].name;
    byId('gov-retrieved').value=docs.flatMap(d=>(d.chunks||[]).map(c=>c.id)).join(', ');
    const reqs=[...new Set(docs.flatMap(d=>(d.chunks||[]).map(c=>c.requirement_id).filter(Boolean)))];
    byId('gov-pack').value=JSON.stringify({id:'my-policy',version:'1.0',requirements:reqs.map(id=>({id,min_independent_sources:1}))},null,2);
    packEditor('gov-pack-editor','gov-pack');passageList();
    govStatus('Documents loaded with a starter policy: one requirement per requirement_id. Untick passages your search did not return.');}
  catch(error){govStatus(error.message);}
});
byId('gov-test-form').addEventListener('submit',async event=>{
  event.preventDefault();const epoch=sessionEpoch;
  try{
    if(!gov.docs)throw Error('Load documents first, or use the sample data.');
    const pack=govJson(byId('gov-pack').value,'Policy');
    const retrieved=govIds(byId('gov-retrieved').value);
    if(!retrieved.length)throw Error('Choose at least one passage.');
    const body={pack,documents:gov.docs,retrieved};
    const q=byId('gov-question').value.trim();if(q)body.question=q;
    if(gov.usingSample)body.as_of=gov.example.as_of;
    govStatus('Checking the evidence…');
    const result=await api('policy/test',body,epoch);
    gov.test=result;gov.pack=pack;
    if(!result.requirements.some(r=>r.requirement_id===gov.selected))gov.selected=result.requirements[0]&&result.requirements[0].requirement_id;
    govRenderTest();govStatus('Checked. '+result.note);govStep('ask');
    window.dispatchEvent(new CustomEvent('qr:check',{detail:result}));
    govHealth(true);
  }catch(error){if(epoch===sessionEpoch)govStatus(error.message);}
});

function govHeadline(r){
  const s=r.summary,ok=r.requirements.filter(x=>x.verdict==='ADMIT').length,n=r.requirements.length;
  if(r.verdict==='REFUSE')return 'Evidence contradicts '+r.requirements.filter(x=>x.verdict==='REFUSE').map(x=>human(x.requirement_id)).join(', ')+'. Do not answer from these passages.';
  if(r.verdict==='INCONCLUSIVE')return (n-ok)+' of '+n+' requirements are missing evidence: '+r.requirements.filter(x=>x.verdict==='INCONCLUSIVE').map(x=>human(x.requirement_id)).join(', ')+'.';
  const cautions=[];
  if(s.qualified_requirements)cautions.push(plural(s.qualified_requirements,'relies','rely')+' on conditional wording');
  if(s.single_origin_requirements)cautions.push(plural(s.single_origin_requirements,'rests','rest')+' on a single source');
  return cautions.length?'Every requirement has supporting evidence, but '+cautions.join(' and ')+'. Review before relying on it.':'Every requirement has supporting evidence.';
}
function govSpanText(span){
  const p=govEl('p','gov-span-text');let at=0;
  for(const q of span.qualifiers){
    if(q.start>at)p.append(document.createTextNode(span.text.slice(at,q.start)));
    const mark=textEl('mark',span.text.slice(q.start,q.end));mark.title=q.kind;p.append(mark);at=q.end;
  }
  if(at<span.text.length)p.append(document.createTextNode(span.text.slice(at)));
  return p;
}
function govRenderTest(){
  const r=gov.test,box=byId('gov-test-result');box.replaceChildren();box.hidden=false;
  const s=r.summary;
  const verdict=govEl('div','gov-verdict v-'+r.verdict,
    govEl('div','gov-verdict-main',textEl('span','Result','obs-kicker'),textEl('strong',VERDICT_WORD[r.verdict],'gov-verdict-word'),govTag(r.verdict,'gov-verdict-tag')),
    govEl('div','gov-verdict-text',textEl('p',govHeadline(r),'gov-headline'),
      govEl('div','gov-stats',
        govStat(r.requirements.filter(x=>x.verdict==='ADMIT').length+' / '+r.requirements.length,'requirements supported'),
        govStat(s.qualified_requirements,'with conditional wording',s.qualified_requirements?'warn':''),
        govStat(s.single_origin_requirements,'on a single source',s.single_origin_requirements?'warn':''),
        govStat(s.unlinked,'passages not used'))),
    textEl('p',r.note,'gov-fine'));
  const list=govEl('div','gov-reqs');
  for(const req of r.requirements){
    const flags=[];
    if(req.verdict!=='ADMIT')flags.push(req.reasons.map(x=>human(x).toLowerCase()).join(', ')||VERDICT_WORD[req.verdict]);
    const copies=req.spans.filter(x=>x.same_origin_as).length;
    flags.push(req.independent_sources+' of '+plural(req.min_independent_sources,'independent source')+(copies?' · '+plural(copies,'copy','copies')+' counted once':''));
    const words=req.spans.flatMap(x=>x.qualifiers.map(q=>'“'+q.word+'”'));
    if(words.length)flags.push('conditional wording: '+words.join(', '));
    const b=govEl('button','gov-req'+(req.requirement_id===gov.selected?' selected':'')+(req.qualified||req.independent_sources===1?' flagged':''),
      govEl('span','gov-req-head',textEl('span',human(req.requirement_id),'gov-req-name'),textEl('span',VERDICT_WORD[req.verdict],'gov-req-verdict v-'+req.verdict)),
      textEl('span',flags.join(' · '),'gov-req-flag'));
    b.type='button';b.dataset.requirement=req.requirement_id;b.setAttribute('aria-pressed',String(req.requirement_id===gov.selected));
    b.addEventListener('click',()=>{gov.selected=req.requirement_id;govRenderTest();});
    list.append(b);
  }
  if(r.unlinked.length){
    const u=govEl('div','gov-unlinked',textEl('span','Returned by search but not used as evidence','gov-req-flag'));
    for(const x of r.unlinked)u.append(textEl('span',x.chunk_id+' · '+x.origin+(x.revision?' · rev '+x.revision:'')+' — '+x.text,'obs-meta'));
    list.append(u);
  }
  const sel=r.requirements.find(x=>x.requirement_id===gov.selected);
  const spans=govEl('div','gov-spans');
  if(sel){
    spans.append(govEl('div','gov-spans-head',textEl('h2',human(sel.requirement_id)),
      textEl('span','needs '+plural(sel.min_independent_sources,'independent source')+' · has '+sel.independent_sources,'gov-req-flag')));
    if(!sel.spans.length)spans.append(textEl('p','No returned passage supports this requirement.','obs-empty'));
    for(const span of sel.spans){
      const meta=[span.chunk_id,span.origin,span.format,span.revision&&('rev '+span.revision),span.section].filter(Boolean).join(' · ');
      let note,tone;
      if(span.status!=='SUPPORTS'){note=span.status+': not counted as support.';tone='muted';}
      else if(span.same_origin_as){note='Same origin as '+span.same_origin_as+': counted once, not twice.';tone='warn';}
      else if(!span.counts_as_origin){note='Not counted: too old, out of scope or from the wrong authority.';tone='warn';}
      else if(span.qualifiers.length){note='Counted as support. The check does not read the highlighted condition, so a person should.';tone='warn';}
      else{note='Counted. Source: '+span.origin+'.';tone='ok';}
      spans.append(govEl('article','gov-span',textEl('span',meta,'obs-meta'),govSpanText(span),textEl('span',note,'gov-note '+tone)));
    }
  }
  const code=textEl('pre','curl -s -X POST "'+location.origin+'/api/policy/test" \\\n  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\\n  -d @request.json   # {"pack":…, "documents":…, "retrieved":[…]}','gov-code');
  spans.append(govEl('details','advanced',textEl('summary','Use from code'),code,textEl('p','More clients on the Connect page.','hint')));
  box.append(verdict,govEl('div','gov-split',list,spans));
}

// ---------- Health ----------
async function govHealth(silent){
  const epoch=sessionEpoch;
  try{
    const body={far_limit:Number(byId('gov-far').value)||0.10};
    if(gov.pack&&gov.test){body.pack=gov.pack;body.test=gov.test;}
    const bench=await govFile(byId('gov-bench'),'Benchmark report');if(bench)body.benchmark=bench;
    if(!silent)govStatus('Running health checks…');
    const result=await api('policy/advise',body,epoch);
    gov.health=result;gov.healthFor=gov.test;
    govRenderAdvice(result);
    window.dispatchEvent(new CustomEvent('qr:health',{detail:result}));
    if(!silent)govStatus(plural(result.findings.length,'finding')+(body.pack?'':' · check an answer to include policy and evidence checks')+'. '+result.note);
    return result;
  }catch(error){if(epoch===sessionEpoch&&!silent)govStatus(error.message);return null;}
}
byId('gov-advise-form').addEventListener('submit',event=>{event.preventDefault();govHealth(false).then(r=>{if(r)govStep('health');});});
function govRenderAdvice(result){
  const box=byId('gov-advise-result');box.replaceChildren();box.hidden=false;
  const c=result.counts;
  const filters=govEl('div','gov-filters');
  const items=govEl('div','gov-findings');
  const draw=()=>{
    filters.replaceChildren();
    for(const [key,label,n] of [['all','All',result.findings.length],['ERROR',SEVERITY_WORD.ERROR,c.ERROR],['WARN',SEVERITY_WORD.WARN,c.WARN],['INFO',SEVERITY_WORD.INFO,c.INFO]]){
      const b=textEl('button',label+' · '+n,'gov-pill'+(gov.filter===key?' selected':''));b.type='button';b.setAttribute('aria-pressed',String(gov.filter===key));
      b.addEventListener('click',()=>{gov.filter=key;draw();});filters.append(b);
    }
    items.replaceChildren();
    const shown=result.findings.filter(f=>gov.filter==='all'||f.severity===gov.filter);
    if(!shown.length)items.append(textEl('p','Nothing at this level.','obs-empty'));
    for(const f of shown){
      items.append(govEl('details','gov-finding sev-'+f.severity,
        govEl('summary','',textEl('span',SEVERITY_WORD[f.severity],'gov-sev'),textEl('span',f.title,'gov-title'),textEl('span',f.area+' · '+f.where,'obs-meta')),
        govEl('div','gov-finding-body',
          govEl('div','',textEl('span','What we checked','obs-kicker'),textEl('p',f.checked),textEl('span','How to fix it','obs-kicker'),textEl('p',f.fix)),
          govEl('div','',textEl('span','From code','obs-kicker'),textEl('pre',f.code,'gov-code')))));
    }
  };
  draw();
  const headline=c.ERROR?plural(c.ERROR,'thing')+' to fix before relying on results'+(c.WARN?', and '+c.WARN+' to review':'')+'.':
    (c.WARN?plural(c.WARN,'thing')+' to review. Nothing blocks you.':'All clear. Nothing to fix or review.');
  box.append(govEl('div','card health-head '+(c.ERROR?'bad':c.WARN?'warn':'ok'),textEl('strong',headline,'gov-headline'),
    textEl('span',result.blocks_promotion?'Policy changes cannot be promoted until the items to fix are resolved.':'Policy changes can be promoted after review.','hint')),filters,items);
}

// ---------- Policy changes ----------
function govCurrentCase(){
  if(!gov.docs)return null;
  const chosen=new Set(govIds(byId('gov-retrieved').value)),evidence=[];
  const at=gov.usingSample?gov.example.as_of:new Date().toISOString().replace(/\.\d+Z$/,'Z');
  for(const doc of gov.docs)for(const c of doc.chunks||[])if(chosen.has(c.id)&&c.requirement_id&&c.status)
    evidence.push({id:c.id,requirement_id:c.requirement_id,origin:doc.origin,source_ref:doc.id+'#'+c.id,status:c.status,observed_at:c.observed_at||doc.observed_at||at});
  const q=byId('gov-question').value.trim();
  return {id:'your-current-check',...(q?{question:q}:{}),evidence};
}
function govPrepareChanges(){
  if(!gov.branchTouched&&byId('gov-pack').value.trim()){
    let proposed;
    if(gov.usingSample&&gov.example)proposed=gov.example.branch_pack;
    else{proposed=JSON.parse(byId('gov-pack').value);proposed.version=(proposed.version||'1')+'-proposed';}
    byId('gov-branch').value=JSON.stringify(proposed,null,2);
  }
  packEditor('gov-branch-editor','gov-branch',()=>{gov.branchTouched=true;});
  if(!gov.ownCases){
    const current=govCurrentCase();
    const sample=gov.usingSample&&gov.example?gov.example.cases:[];
    // On untouched sample data the current check equals a recorded search: do not count it twice.
    const key=c=>c.evidence.map(e=>e.id).sort().join('|');
    const dup=current&&sample.some(s=>key(s)===key(current));
    gov.cases=[...sample,...(current&&current.evidence.length&&!dup?[current]:[])];
    byId('gov-cases-label').textContent=gov.cases.length?'Compared on '+plural(gov.cases.length,'test case')+': '+(sample.length?plural(sample.length,'recorded search')+' from the sample'+(current&&!dup?' plus your current check':''):'your current check')+'. Add labelled cases under Advanced to also see right- and wrong-answer rates.':'Check an answer first, or add test cases under Advanced.';
  }
}
byId('gov-cases').addEventListener('change',async()=>{
  try{const cases=await govFile(byId('gov-cases'),'Test cases file');if(!Array.isArray(cases))throw Error('Test cases file must be a JSON list.');
    gov.cases=cases;gov.ownCases=true;byId('gov-cases-label').textContent=plural(cases.length,'test case')+' loaded from '+byId('gov-cases').files[0].name;}
  catch(error){govStatus(error.message);}
});
byId('gov-replay-form').addEventListener('submit',async event=>{
  event.preventDefault();const epoch=sessionEpoch;
  try{
    if(!byId('gov-pack').value.trim())throw Error('Check an answer first: the proposed policy starts from the current one.');
    if(!gov.cases||!gov.cases.length)throw Error('No test cases yet. Check an answer first, or add test cases under Advanced.');
    const cases=gov.cases.map(c=>{const x={id:c.id,evidence:c.evidence};if(c.question)x.question=c.question;if(typeof c.expect_admit==='boolean')x.expect_admit=c.expect_admit;return x;});
    const body={base:govJson(byId('gov-pack').value,'Current policy'),branch:govJson(byId('gov-branch').value,'Proposed policy'),cases};
    if(gov.usingSample&&!gov.ownCases)body.as_of=gov.example.as_of;
    govStatus('Comparing…');
    const result=await api('policy/replay',body,epoch);
    govRenderReplay(result);govStatus(result.note);govStep('changes');
  }catch(error){if(epoch===sessionEpoch)govStatus(error.message);}
});
function govRenderReplay(r){
  const box=byId('gov-replay-result');box.replaceChildren();box.hidden=false;
  const e=r.effects,labeled=r.labeled.expect_admit+r.labeled.expect_refusal;
  const headline=r.flipped?plural(r.flipped,'result')+' of '+r.cases+' would change under the proposed policy.':'No result would change. The proposed policy behaves like the current one on these cases.';
  const diff=govEl('pre','gov-code gov-diff');
  if(!r.pack_diff.length)diff.append(document.createTextNode('No requirement changes.'));
  for(const d of r.pack_diff){
    if(d.change==='modified'){
      diff.append(textEl('span','- '+d.requirement_id+'.'+d.field+': '+JSON.stringify(d.from),'del'),textEl('span','+ '+d.requirement_id+'.'+d.field+': '+JSON.stringify(d.to),'add'));
    }else diff.append(textEl('span',(d.change==='added'?'+ ':'- ')+d.requirement_id+' ('+d.change+')',d.change==='added'?'add':'del'));
  }
  const rate=(label,a,b,better)=>govEl('div','gov-rate',textEl('span',label),textEl('span',pct(a)+' → '+pct(b),'mono'+(a!==null&&b!==null&&a!==b?((b<a)===(better==='lower')?' ok':' warn'):'')));
  const rates=govEl('div','gov-rates',textEl('span','Rates','obs-kicker'));
  if(labeled){rates.append(rate('Wrong answers given (lower is better)',r.base.false_admission_rate,r.branch.false_admission_rate,'lower'),
    rate('Questions answered (higher is better)',r.base.answer_rate,r.branch.answer_rate,'higher'));}
  else rates.append(textEl('p','Add test cases labelled with expect_admit under Advanced to see how often answers are right or wrong.','gov-fine'));
  const table=govEl('table','gov-table');
  const heads=['Case','Now','Proposed','Expected','Effect'];
  table.append(govEl('thead','',govEl('tr','',...heads.map(h=>textEl('th',h)))));
  const tb=govEl('tbody','');
  if(!r.flips.length){const td=textEl('td','No result changed.');td.colSpan=5;tb.append(govEl('tr','',td));}
  for(const f of r.flips){
    const cells=[textEl('td',f.id+(f.question?' — '+f.question:'')),govEl('td','',textEl('span',VERDICT_WORD[f.from]+' ','v-'+f.from),govTag(f.from)),
      govEl('td','',textEl('span',VERDICT_WORD[f.to]+' ','v-'+f.to),govTag(f.to)),
      textEl('td',f.expect_admit===null?'not labelled':(f.expect_admit?'should answer':'should not answer')),textEl('td',f.effect==='unlabeled'?'—':f.effect.replaceAll('_',' '))];
    cells.forEach((c,i)=>c.dataset.label=heads[i]);tb.append(govEl('tr','',...cells));
  }
  table.append(tb);
  box.append(govEl('div','card health-head '+(r.flipped?'warn':'ok'),textEl('strong',headline,'gov-headline')),
    govEl('div','gov-stats',govStat(r.base.admit+' → '+r.branch.admit,'answers supported'),govStat(r.flipped,'results changed'),
      govStat(e.false_admission_removed,'wrong answers prevented',e.false_admission_removed?'ok':''),govStat(e.correct_answer_lost,'right answers lost',e.correct_answer_lost?'warn':'')),
    govEl('div','table-wrap gov-table-wrap',table),
    govEl('div','gov-split',govEl('div','',textEl('span','What changes · '+r.base.pack+' → '+r.branch.pack,'obs-kicker'),diff),rates),
    textEl('p','Nothing is applied here. Promoting a policy change is a separate signed review, available once Health shows nothing to fix.','gov-fine'));
}

// ---------- Alternatives ----------
async function govLoadSiblings(){
  const ex=(await api('policy/example',{},sessionEpoch)).siblings_example;
  gov.sib=ex;gov.cands=ex.candidates;
  byId('gov-sib-function').value=ex.function;byId('gov-sib-contracts').value=JSON.stringify(ex.contracts,null,2);
  byId('gov-sib-label').textContent=ex.candidates.length+' candidates · illustrative, from '+ex.source+'. '+ex.note;
}
byId('gov-sib-example').addEventListener('click',async()=>{try{await govLoadSiblings();govStatus('Sample loaded. Choose Compare alternatives.');}catch(error){govStatus(error.message);}});
byId('gov-sib-cands').addEventListener('change',async()=>{
  try{const c=await govFile(byId('gov-sib-cands'),'Candidates file');if(!Array.isArray(c))throw Error('Candidates file must be a JSON list.');
    gov.cands=c;gov.sib=null;byId('gov-sib-label').textContent=plural(c.length,'candidate')+' loaded from '+byId('gov-sib-cands').files[0].name;}
  catch(error){govStatus(error.message);}
});
byId('gov-sib-form').addEventListener('submit',async event=>{
  event.preventDefault();const epoch=sessionEpoch;
  try{
    if(!gov.cands)throw Error('Load candidates first, or use the sample data.');
    const body={function:byId('gov-sib-function').value.trim(),contracts:govJson(byId('gov-sib-contracts').value,'Requirement sets'),candidates:gov.cands};
    if(gov.sib&&gov.cands===gov.sib.candidates)body.as_of=gov.sib.as_of;
    govStatus('Comparing alternatives…');
    const r=await api('policy/siblings',body,epoch);
    govRenderSiblings(r);govStatus(r.coverage.statement);
  }catch(error){if(epoch===sessionEpoch)govStatus(error.message);}
});
function govRenderSiblings(r){
  const box=byId('gov-sib-result');box.replaceChildren();box.hidden=false;
  const names=Object.keys(r.contracts);
  const stats=govEl('div','gov-stats');
  for(const n of names){const c=r.contracts[n];
    stats.append(govStat(c.feasible.length+' · '+c.rejected.length+' · '+c.unknown.length,human(n)+': works · fails · unknown'));}
  stats.append(govStat(r.regime_boundaries.length,'change between requirement sets',r.regime_boundaries.length?'warn':''));
  const table=govEl('table','gov-table gov-matrix');
  const heads=['Candidate','Family',...names.map(human)];
  table.append(govEl('thead','',govEl('tr','',...heads.map(h=>textEl('th',h)))));
  const tb=govEl('tbody','');
  for(const row of r.matrix){
    const cells=[textEl('td',row.candidate,'mono'),textEl('td',row.mechanism_family||'—')];
    for(const n of names){const c=row.contracts[n];
      const missing=c.requirements.filter(q=>q.status!=='SAT').map(q=>human(q.requirement_id));
      const td=govEl('td','',textEl('span',STATUS_WORD[c.status],'gov-cell s-'+c.status));
      if(missing.length)td.append(textEl('span',' '+missing.join(', '),'obs-meta'));
      cells.push(td);}
    cells.forEach((c,i)=>c.dataset.label=heads[i]);tb.append(govEl('tr','',...cells));
  }
  table.append(tb);
  const sib=govEl('div','gov-rates',textEl('span','Interchangeable under each requirement set','obs-kicker'));
  for(const n of names){const c=r.contracts[n];
    sib.append(textEl('p',human(n)+': '+(c.siblings.length?c.siblings.join(', ')+' ('+c.sibling_pairs+' pairs)':'no two candidates are known to work.'),'gov-fine'));}
  const bounds=govEl('div','gov-rates',textEl('span','Where the answer changes','obs-kicker'));
  if(!r.regime_boundaries.length)bounds.append(textEl('p','No candidate changes between these requirement sets.','gov-fine'));
  for(const b of r.regime_boundaries)bounds.append(textEl('p',b.candidate+': '+STATUS_WORD[b.from].toLowerCase()+' under '+human(b.from_contract)+', '+STATUS_WORD[b.to].toLowerCase()+' under '+human(b.to_contract)+(b.deciding_requirements.length?' · decided by '+b.deciding_requirements.map(human).join(', '):''),'gov-fine '+(b.to==='UNSAT'?'bad':'')));
  const probes=govEl('details','gov-finding',govEl('summary','',textEl('span','Next','gov-sev'),textEl('span',plural(r.probes.length,'open question')+' to test next','gov-title')));
  const list=govEl('ul','gov-probes');
  for(const p of r.probes)list.append(textEl('li','Does '+p.candidate+' meet “'+human(p.requirement_id)+'” ('+human(p.contract)+')?'+(p.missing_sources?' Needs '+plural(p.missing_sources,'more independent source')+'.':'')));
  probes.append(list);
  const guards=govEl('ul','gov-probes');for(const g of r.guards)guards.append(textEl('li',g));
  box.append(stats,govEl('div','table-wrap gov-table-wrap',table),govEl('div','gov-split',sib,bounds),probes,
    govEl('details','advanced',textEl('summary','How to read this'),guards));
}

// Called by the shell when a screen opens: every screen starts with something to see.
async function govEnter(view){
  try{
    if((view==='ask'||view==='changes')&&!gov.docs)await govLoadSample();
    if(view==='changes')govPrepareChanges();
    if(view==='health'&&(!gov.health||gov.healthFor!==gov.test))await govHealth(true);
    if(view==='alternatives'&&!gov.cands)await govLoadSiblings();
  }catch(error){govStatus(error.message);}
}
