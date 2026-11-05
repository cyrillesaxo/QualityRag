'use strict';
// Governance tab: policy tester, advisor and branch replay. Uses api(), byId(), textEl() and
// sessionEpoch from app.js. DOM APIs only (CSP: no inline styles, no innerHTML).
const gov={docs:null,cases:null,test:null,pack:null,selected:null,filter:'all',example:null};

function governanceReset(){
  Object.assign(gov,{docs:null,cases:null,test:null,pack:null,selected:null,filter:'all',example:null});
  for(const id of ['gov-test-result','gov-advise-result','gov-replay-result']){const n=byId(id);n.replaceChildren();n.hidden=true;}
  byId('gov-status').textContent='';byId('gov-docs-label').textContent='No documents loaded.';byId('gov-cases-label').textContent='No cases loaded.';
}
function govEl(tag,cls,...children){const n=document.createElement(tag);if(cls)n.className=cls;for(const c of children)n.append(c);return n;}
function govStatus(text){byId('gov-status').textContent=text;}
function govJson(text,name){try{return JSON.parse(text);}catch(_e){throw Error(name+' is not valid JSON.');}}
async function govFile(input,name){
  const file=input.files[0];if(!file)return null;
  if(file.size>450000)throw Error(name+' exceeds 450 KB.');
  return govJson(await file.text(),name);
}
function govIds(text){return text.split(/[\s,]+/).map(s=>s.trim()).filter(Boolean);}
function pct(x){return x===null||x===undefined?'—':(x*100).toFixed(1)+'%';}

// Tabs (keyboard: arrow keys move between tabs).
const govTabs=['test','advise','replay'];
function govShow(name){
  for(const t of govTabs){const tab=byId('gov-tab-'+t),on=t===name;tab.setAttribute('aria-selected',String(on));tab.tabIndex=on?0:-1;byId('gov-'+t).hidden=!on;}
}
govTabs.forEach((t,i)=>{
  const tab=byId('gov-tab-'+t);
  tab.addEventListener('click',()=>govShow(t));
  tab.addEventListener('keydown',ev=>{
    if(ev.key!=='ArrowRight'&&ev.key!=='ArrowLeft')return;
    const next=govTabs[(i+(ev.key==='ArrowRight'?1:govTabs.length-1))%govTabs.length];
    govShow(next);byId('gov-tab-'+next).focus();
  });
});

// Policy tester
byId('gov-example').addEventListener('click',async()=>{
  const epoch=sessionEpoch;
  try{
    const ex=await api('policy/example',{},epoch);
    gov.example=ex;gov.docs=ex.documents;gov.cases=ex.cases;
    byId('gov-question').value=ex.question;byId('gov-pack').value=JSON.stringify(ex.pack,null,2);
    byId('gov-retrieved').value=ex.retrieved.join(', ');byId('gov-branch').value=JSON.stringify(ex.branch_pack,null,2);
    const chunks=ex.documents.reduce((s,d)=>s+d.chunks.length,0);
    byId('gov-docs-label').textContent=ex.documents.length+' documents · '+chunks+' chunks · from '+ex.source;
    byId('gov-cases-label').textContent=ex.cases.length+' recorded retrievals of the example question (unlabeled)';
    govStatus('Example loaded. Run the gate.');
  }catch(error){if(epoch===sessionEpoch)govStatus(error.message);}
});
byId('gov-docs').addEventListener('change',async()=>{
  try{const docs=await govFile(byId('gov-docs'),'Documents file');if(!Array.isArray(docs))throw Error('Documents file must be a JSON list.');
    gov.docs=docs;byId('gov-docs-label').textContent=docs.length+' documents loaded from '+byId('gov-docs').files[0].name;}
  catch(error){govStatus(error.message);}
});
byId('gov-test-form').addEventListener('submit',async event=>{
  event.preventDefault();const epoch=sessionEpoch;
  try{
    if(!gov.docs)throw Error('Load documents first, or load the example.');
    const pack=govJson(byId('gov-pack').value,'PackSpec');
    const body={pack,documents:gov.docs,retrieved:govIds(byId('gov-retrieved').value)};
    const q=byId('gov-question').value.trim();if(q)body.question=q;
    if(gov.example&&body.documents===gov.example.documents)body.as_of=gov.example.as_of;
    govStatus('Running the gate…');
    const result=await api('policy/test',body,epoch);
    gov.test=result;gov.pack=pack;
    if(!result.requirements.some(r=>r.requirement_id===gov.selected))gov.selected=result.requirements[0]&&result.requirements[0].requirement_id;
    govRenderTest();govStatus('Gate evaluated. '+result.note);
  }catch(error){if(epoch===sessionEpoch)govStatus(error.message);}
});

function govStat(value,label,tone){return govEl('div','gov-stat'+(tone?' '+tone:''),textEl('span',String(value),'gov-stat-value'),textEl('span',label,'gov-stat-label'));}
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
    govEl('div','',textEl('span','Gate verdict','obs-kicker'),textEl('strong',r.verdict,'gov-verdict-word')),
    govEl('div','gov-stats',
      govStat(r.requirements.filter(x=>x.verdict==='ADMIT').length+' / '+r.requirements.length,'requirements admitted'),
      govStat(s.qualified_requirements,'admitted with a qualifier',s.qualified_requirements?'warn':''),
      govStat(s.single_origin_requirements,'admitted on one origin',s.single_origin_requirements?'warn':''),
      govStat(s.unlinked,'retrieved, not counted')),
    textEl('p',r.evaluated+' '+r.note,'gov-fine'));
  const list=govEl('div','gov-reqs');
  for(const req of r.requirements){
    const flags=[];
    if(req.verdict!=='ADMIT')flags.push(req.reasons.join(', ')||req.verdict);
    const copies=req.spans.filter(x=>x.same_origin_as).length;
    flags.push(req.independent_sources+' of '+req.min_independent_sources+' required origin'+(req.min_independent_sources===1?'':'s')+(copies?' · '+copies+' copy collapsed':''));
    const words=req.spans.flatMap(x=>x.qualifiers.map(q=>'“'+q.word+'”'));
    if(words.length)flags.push('qualified: '+words.join(', '));
    const b=govEl('button','gov-req'+(req.requirement_id===gov.selected?' selected':'')+(req.qualified||req.independent_sources===1?' flagged':''),
      govEl('span','gov-req-head',textEl('span',req.requirement_id,'mono'),textEl('span',req.verdict,'mono v-'+req.verdict)),
      textEl('span',flags.join(' · '),'gov-req-flag'));
    b.type='button';b.setAttribute('aria-pressed',String(req.requirement_id===gov.selected));
    b.addEventListener('click',()=>{gov.selected=req.requirement_id;govRenderTest();});
    list.append(b);
  }
  if(r.unlinked.length){
    const u=govEl('div','gov-unlinked',textEl('span','Retrieved, not counted','gov-req-flag'));
    for(const x of r.unlinked)u.append(textEl('span',x.chunk_id+' · '+x.origin+(x.revision?' · rev '+x.revision:'')+' — '+x.text,'obs-meta'));
    list.append(u);
  }
  const sel=r.requirements.find(x=>x.requirement_id===gov.selected);
  const spans=govEl('div','gov-spans');
  if(sel){
    spans.append(govEl('div','gov-spans-head',textEl('h3',sel.requirement_id,'mono'),
      textEl('span','needs '+sel.min_independent_sources+' origin'+(sel.min_independent_sources===1?'':'s')+' · has '+sel.independent_sources,'gov-req-flag')));
    if(!sel.spans.length)spans.append(textEl('p','No retrieved chunk is linked to this requirement.','obs-empty'));
    for(const span of sel.spans){
      const meta=[span.chunk_id,span.origin,span.format,span.revision&&('rev '+span.revision),span.section].filter(Boolean).join(' · ');
      let note,tone;
      if(span.status!=='SUPPORTS'){note=span.status+': not counted as support.';tone='muted';}
      else if(span.same_origin_as){note='Same origin as '+span.same_origin_as+': counted once, not twice.';tone='warn';}
      else if(!span.counts_as_origin){note='Not counted: rejected by age, scope or authority (see the requirement reasons).';tone='warn';}
      else if(span.qualifiers.length){note='Counted as SUPPORTS. The gate does not evaluate the highlighted condition.';tone='warn';}
      else{note='Counted. Origin: '+span.origin+'.';tone='ok';}
      spans.append(govEl('article','gov-span',textEl('span',meta,'obs-meta'),govSpanText(span),textEl('span',note,'gov-note '+tone)));
    }
  }
  const code=textEl('pre','curl -s -X POST "$QUALITYRAG_ENDPOINT/api/policy/test" \\\n  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\\n  -d @request.json   # {"pack":…, "documents":…, "retrieved":[…]}','gov-code');
  spans.append(textEl('span','Same request from code','obs-kicker'),code);
  box.append(verdict,govEl('div','gov-split',list,spans));
}

// Advisor
byId('gov-advise-form').addEventListener('submit',async event=>{
  event.preventDefault();const epoch=sessionEpoch;
  try{
    const body={far_limit:Number(byId('gov-far').value)};
    if(gov.pack&&gov.test){body.pack=gov.pack;body.test=gov.test;}
    const bench=await govFile(byId('gov-bench'),'Benchmark report');if(bench)body.benchmark=bench;
    govStatus('Running the advisor…');
    const result=await api('policy/advise',body,epoch);
    govRenderAdvice(result);
    govStatus(result.findings.length+' finding'+(result.findings.length===1?'':'s')+(body.pack?'':' (run the policy tester first to include pack and evidence checks)')+'. '+result.note);
  }catch(error){if(epoch===sessionEpoch)govStatus(error.message);}
});
function govRenderAdvice(result){
  const box=byId('gov-advise-result');box.replaceChildren();box.hidden=false;
  const c=result.counts;
  const filters=govEl('div','gov-filters');
  const shown=()=>result.findings.filter(f=>gov.filter==='all'||f.severity===gov.filter);
  const items=govEl('div','gov-findings');
  const draw=()=>{
    filters.replaceChildren();
    for(const [key,label,n] of [['all','All',result.findings.length],['ERROR','Errors',c.ERROR],['WARN','Warnings',c.WARN],['INFO','Info',c.INFO]]){
      const b=textEl('button',label+' · '+n,'gov-pill'+(gov.filter===key?' selected':''));b.type='button';b.setAttribute('aria-pressed',String(gov.filter===key));
      b.addEventListener('click',()=>{gov.filter=key;draw();});filters.append(b);
    }
    items.replaceChildren();
    if(!shown().length)items.append(textEl('p','No findings at this severity.','obs-empty'));
    for(const f of shown()){
      const d=govEl('details','gov-finding sev-'+f.severity,
        govEl('summary','',textEl('span',f.severity,'gov-sev'),textEl('span',f.area,'mono gov-area'),textEl('span',f.title,'gov-title'),textEl('span',f.where,'obs-meta')),
        govEl('div','gov-finding-body',
          govEl('div','',textEl('span','What was checked','obs-kicker'),textEl('p',f.checked),textEl('span','Fix','obs-kicker'),textEl('p',f.fix)),
          govEl('div','',textEl('span','From code','obs-kicker'),textEl('pre',f.code,'gov-code'))));
      items.append(d);
    }
  };
  draw();
  const banner=textEl('p',result.blocks_promotion?'Errors block promotion of a policy branch until they are fixed.':'No blocking errors.','gov-fine '+(result.blocks_promotion?'bad':'ok'));
  box.append(govEl('div','gov-stats',govStat(c.ERROR,'errors',c.ERROR?'bad':''),govStat(c.WARN,'warnings',c.WARN?'warn':''),govStat(c.INFO,'info')),banner,filters,items);
}

// Branch replay
byId('gov-cases').addEventListener('change',async()=>{
  try{const cases=await govFile(byId('gov-cases'),'Cases file');if(!Array.isArray(cases))throw Error('Cases file must be a JSON list.');
    gov.cases=cases;byId('gov-cases-label').textContent=cases.length+' cases loaded from '+byId('gov-cases').files[0].name;}
  catch(error){govStatus(error.message);}
});
byId('gov-replay-form').addEventListener('submit',async event=>{
  event.preventDefault();const epoch=sessionEpoch;
  try{
    if(!gov.cases)throw Error('Load recorded cases first, or load the example in the Policy tester.');
    const body={base:govJson(byId('gov-pack').value,'Current PackSpec'),branch:govJson(byId('gov-branch').value,'Branch PackSpec'),cases:gov.cases};
    if(gov.example&&gov.cases===gov.example.cases)body.as_of=gov.example.as_of;
    govStatus('Replaying…');
    const result=await api('policy/replay',body,epoch);
    govRenderReplay(result);govStatus(result.flipped+' verdict'+(result.flipped===1?'':'s')+' changed across '+result.cases+' cases. '+result.note);
  }catch(error){if(epoch===sessionEpoch)govStatus(error.message);}
});
function govRenderReplay(r){
  const box=byId('gov-replay-result');box.replaceChildren();box.hidden=false;
  const e=r.effects,labeled=r.labeled.expect_admit+r.labeled.expect_refusal;
  const diff=govEl('pre','gov-code gov-diff');
  if(!r.pack_diff.length)diff.append(document.createTextNode('No requirement changes.'));
  for(const d of r.pack_diff){
    if(d.change==='modified'){
      diff.append(textEl('span','- '+d.requirement_id+'.'+d.field+': '+JSON.stringify(d.from),'del'),textEl('span','+ '+d.requirement_id+'.'+d.field+': '+JSON.stringify(d.to),'add'));
    }else diff.append(textEl('span',(d.change==='added'?'+ ':'- ')+d.requirement_id+' ('+d.change+')',d.change==='added'?'add':'del'));
  }
  const rate=(label,a,b,better)=>govEl('div','gov-rate',textEl('span',label),textEl('span',pct(a)+' → '+pct(b)+(a===null?' (needs expect_admit labels)':''),'mono'+(a!==null&&b!==null&&a!==b?((b<a)===(better==='lower')?' ok':' warn'):'')));
  const table=govEl('table','gov-table');
  table.append(govEl('thead','',govEl('tr','',...['Case','Base','Branch','Label','Effect'].map(h=>textEl('th',h)))));
  const tb=govEl('tbody','');
  if(!r.flips.length)tb.append(govEl('tr','',textEl('td','No verdict changed.')));
  const heads=['Case','Base','Branch','Label','Effect'];
  for(const f of r.flips){
    const cells=[textEl('td',f.id+(f.question?' — '+f.question:'')),textEl('td',f.from,'mono'),textEl('td',f.to,'mono'),
      textEl('td',f.expect_admit===null?'unlabeled':(f.expect_admit?'should admit':'should refuse')),textEl('td',f.effect.replaceAll('_',' '))];
    cells.forEach((c,i)=>c.dataset.label=heads[i]);tb.append(govEl('tr','',...cells));
  }
  table.append(tb);
  box.append(
    govEl('div','gov-stats',govStat(r.base.admit+' → '+r.branch.admit,'admitted'),govStat(r.flipped,'verdicts changed'),
      govStat(e.false_admission_removed,'false admissions removed',e.false_admission_removed?'ok':''),govStat(e.correct_answer_lost,'correct answers lost',e.correct_answer_lost?'warn':'')),
    govEl('div','gov-split',govEl('div','',textEl('span','Policy diff · '+r.base.pack+' → '+r.branch.pack,'obs-kicker'),diff),
      govEl('div','gov-rates',textEl('span','Rates over '+labeled+' labeled case'+(labeled===1?'':'s'),'obs-kicker'),
        rate('False-admission rate (lower is better)',r.base.false_admission_rate,r.branch.false_admission_rate,'lower'),
        rate('Answer rate (higher is better)',r.base.answer_rate,r.branch.answer_rate,'higher'))),
    govEl('div','table-wrap gov-table-wrap',table),
    textEl('p','Promotion is not done here. A branch is promoted through a signed review once the Advisor reports no errors.','gov-fine'));
}
