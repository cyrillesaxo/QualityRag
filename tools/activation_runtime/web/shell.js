'use strict';
// Console shell: sign-in vs workspace, sidebar routing (#/view), Home summary, badges,
// getting-started steps and the Connect page. Listens for qr:* events from app.js and
// governance.js; owns no workspace data itself.
(function(){
  const $=id=>document.getElementById(id);
  const views=[...document.querySelectorAll('[data-view]')];
  const names=views.map(v=>v.dataset.view);
  const shell={switching:false,ready:false,tenant:null,done:new Set()};

  function layout(){
    const connected=!$('workspace').hidden;
    $('signin').hidden=connected&&!shell.switching;
    document.body.classList.toggle('switching',shell.switching);
    document.body.classList.toggle('signed-in',connected);
    for(const id of ['sidebar','ws-name','switch-ws','connect-link','menu-toggle'])$(id).hidden=!connected;
    $('signin-cancel').hidden=!(connected&&shell.switching);
  }
  new MutationObserver(()=>{if($('workspace').hidden===false)shell.switching=false;layout();}).observe($('workspace'),{attributes:true,attributeFilter:['hidden']});

  // Signing in again (another token) is the same form; the old session is discarded by app.js.
  const cancel=document.createElement('button');cancel.type='button';cancel.id='signin-cancel';cancel.className='btn-ghost';cancel.textContent='Cancel';cancel.hidden=true;
  cancel.addEventListener('click',()=>{shell.switching=false;layout();});
  $('connect').append(cancel);
  $('switch-ws').addEventListener('click',()=>{shell.switching=true;layout();$('token').focus();});

  function route(){
    const match=/^#\/([a-z]+)/.exec(location.hash);
    const view=match&&names.includes(match[1])?match[1]:'home';
    for(const v of views)v.hidden=v.dataset.view!==view;
    for(const a of document.querySelectorAll('[data-nav]')){
      if(a.dataset.nav===view)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');
    }
    if($('gov-status'))$('gov-status').textContent='';
    $('sidebar').classList.remove('open');$('menu-toggle').setAttribute('aria-expanded','false');
    if(view==='tree'&&typeof gardenUpdate==='function')gardenUpdate();
    if(view==='connect'){snippet(shell.snippet||'curl');step('connect');}
    if(view==='health')step('health');
    if(typeof govEnter==='function'&&!$('workspace').hidden)govEnter(view);
    return view;
  }
  window.addEventListener('hashchange',()=>{route();$('main').focus({preventScroll:true});});
  $('menu-toggle').addEventListener('click',()=>{
    const open=!$('sidebar').classList.contains('open');
    $('sidebar').classList.toggle('open',open);$('menu-toggle').setAttribute('aria-expanded',String(open));
  });

  function step(name){
    shell.done.add(name);
    for(const li of document.querySelectorAll('#home-steps li'))li.classList.toggle('done',shell.done.has(li.dataset.step));
  }
  window.addEventListener('qr:step',e=>step(e.detail));

  window.addEventListener('qr:ready',e=>{
    const {who,state,suggestions}=e.detail;
    const fresh=shell.tenant!==who.tenant||!shell.ready;
    shell.ready=true;shell.tenant=who.tenant;
    $('ws-name').textContent=who.tenant+' · '+who.scopes.join(', ');
    const branches=Object.values(state.branches);
    const open=Object.values(state.branches).filter(b=>{const ev=b.events.map(id=>state.events[id]);const last=ev.map(x=>x.operation).lastIndexOf('CHALLENGE');return last>=0&&!ev.slice(last+1).some(x=>x.operation==='TEST');}).length;
    $('home-tree').textContent=branches.length?branches.length+' branch'+(branches.length===1?'':'es')+(open?' · '+open+' open challenge'+(open===1?'':'s'):''):'No branches yet';
    const n=(suggestions.proposals||[]).length;
    $('badge-review').textContent=String(n);$('badge-review').hidden=!n;
    $('home-title').textContent='Workspace '+who.tenant;
    if(fresh){
      if(!location.hash.startsWith('#/'))history.replaceState(null,'','#/home');
      route();
      if(typeof govHealth==='function')govHealth(true);
    }
  });
  window.addEventListener('qr:health',e=>{
    const c=e.detail.counts,n=c.ERROR+c.WARN;
    $('badge-health').textContent=String(n);$('badge-health').hidden=!n;
    $('badge-health').classList.toggle('bad',c.ERROR>0);
    $('home-health').textContent=c.ERROR?c.ERROR+' to fix'+(c.WARN?' · '+c.WARN+' to review':''):(c.WARN?c.WARN+' to review':'All clear');
  });
  window.addEventListener('qr:check',e=>{
    const word={ADMIT:'Supported',INCONCLUSIVE:'Not enough evidence',REFUSE:'Contradicted'}[e.detail.verdict];
    $('home-check').textContent='Last check: '+word;
  });

  // Connect page
  const origin=location.origin;
  const SNIPPETS={
    curl:['# The token is the same one you pasted to sign in.\ncurl -s -X POST "'+origin+'/api/policy/test" \\\n  -H "Authorization: Bearer $QUALITYRAG_TOKEN" \\\n  -H "Content-Type: application/json" \\\n  -d \'{"pack": {...}, "documents": [...], "retrieved": ["chunk-id"]}\'',
      'Every console action is a POST to /api/<route> with the same token. Routes: policy/test, policy/advise, policy/replay, policy/siblings, gardener/query, gardener/event.'],
    python:['import json\nfrom qualityrag_activation import Client   # sdk/python in the repository\n\nqr = Client("'+origin+'", json.load(open("token.json")))\nex = qr.policy_example()\nresult = qr.policy_test(pack=ex["pack"], documents=ex["documents"], retrieved=ex["retrieved"])\nprint(result["verdict"], result["summary"])\nprint([f["title"] for f in qr.policy_advise(pack=ex["pack"], test=result)["findings"]])',
      'token.json is the signed token as JSON. The client has a method for every console screen.'],
    ts:['import { ActivationClient } from "qualityrag";   // sdk/typescript\n\nconst qr = new ActivationClient("'+origin+'", token);\nconst ex = await qr.policyExample();\nconst result = await qr.policyTest({ pack: ex.pack, documents: ex.documents, retrieved: ex.retrieved });\nconst health = await qr.policyAdvise({ pack: ex.pack, test: result });',
      'Same methods as Python: policyTest, policyAdvise, policyReplay, policySiblings, gardenQuery, gardenEvent.'],
    cli:['python -m tools.activation_runtime.cli garden query --endpoint '+origin+' --token token.json --open-challenge\npython -m tools.activation_runtime.cli garden watch --endpoint '+origin+' --token token.json\npython -m tools.activation_runtime.cli garden query --endpoint '+origin+' --token token.json --depends-on <evidence-id>',
      'watch prints one JSON line per new research event. --depends-on lists what to re-check when a piece of evidence changes.'],
    mcp:['{\n  "mcpServers": {\n    "qualityrag": {\n      "command": "python",\n      "args": ["-m", "tools.activation_runtime.mcp_server"],\n      "cwd": "/path/to/QualityRag",\n      "env": {\n        "QUALITYRAG_ENDPOINT": "'+origin+'",\n        "QUALITYRAG_TOKEN_FILE": "/path/to/agent-token.json"\n      }\n    }\n  }\n}',
      'Add this to your agent\'s MCP configuration (for example .mcp.json). Give agents a read + write token: they can check answers, run health checks, compare policies and alternatives, and propose, challenge and test research branches. Pruning, reopening and validation stay with people.'],
  };
  function snippet(name){
    shell.snippet=name;
    $('connect-endpoint').textContent=origin+'/api';
    $('connect-snippet').textContent=SNIPPETS[name][0];$('connect-note').textContent=SNIPPETS[name][1];
    for(const b of document.querySelectorAll('[data-snippet]'))b.setAttribute('aria-pressed',String(b.dataset.snippet===name));
  }
  for(const b of document.querySelectorAll('[data-snippet]'))b.addEventListener('click',()=>snippet(b.dataset.snippet));
  for(const b of document.querySelectorAll('[data-copy]'))b.addEventListener('click',async()=>{
    const text=$(b.dataset.copy).textContent;
    try{await navigator.clipboard.writeText(text);b.textContent='Copied';}
    catch(_e){const r=document.createRange();r.selectNodeContents($(b.dataset.copy));const s=getSelection();s.removeAllRanges();s.addRange(r);b.textContent='Selected · press Ctrl+C';}
    setTimeout(()=>{b.textContent='Copy';},1800);
  });

  layout();route();
})();
