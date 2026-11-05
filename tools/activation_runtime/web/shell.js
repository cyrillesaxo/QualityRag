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
    for(const id of ['sidebar','ws-name','switch-ws','connect-link','menu-toggle','palette-open'])$(id).hidden=!connected;
    $('crumb-page').hidden=!connected;document.querySelector('.crumb-page-sep').hidden=!connected;
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
    const navItem=document.querySelector('[data-nav="'+view+'"]');
    $('crumb-page').textContent=navItem?navItem.dataset.tip:'';
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

  // Theme: System (follow the OS), Light or Dark; remembered in this browser only.
  const theme=$('theme');
  theme.value=document.documentElement.dataset.theme||'system';
  theme.addEventListener('change',()=>{
    const v=theme.value;
    if(v==='system')delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=v;
    try{if(v==='system')localStorage.removeItem('qr-theme');else localStorage.setItem('qr-theme',v);}catch(_e){/* not remembered */}
  });

  // Go to palette (Ctrl/Cmd+K): every screen by name, filtered as you type.
  const palette=$('palette'),pin=$('palette-input'),plist=$('palette-list');
  const targets=[...document.querySelectorAll('[data-nav]')].map(a=>({view:a.dataset.nav,label:a.dataset.tip}));
  let pick=0;
  function paletteDraw(){
    const q=pin.value.trim().toLowerCase(),hits=targets.filter(x=>!q||x.label.toLowerCase().includes(q));
    pick=Math.min(pick,Math.max(0,hits.length-1));plist.replaceChildren();
    hits.forEach((x,i)=>{
      const li=document.createElement('li'),a=document.createElement('a');
      a.href='#/'+x.view;a.textContent=x.label;if(i===pick)a.setAttribute('aria-current','true');
      a.addEventListener('click',()=>palette.close());li.append(a);plist.append(li);
    });
    if(!hits.length){const li=document.createElement('li');li.className='hint';li.textContent='No screen matches.';plist.append(li);}
    return hits;
  }
  function paletteOpen(){if($('workspace').hidden||palette.open)return;pin.value='';pick=0;paletteDraw();palette.showModal();pin.focus();}
  $('palette-open').addEventListener('click',paletteOpen);
  pin.addEventListener('input',()=>{pick=0;paletteDraw();});
  pin.addEventListener('keydown',e=>{
    const hits=paletteDraw();
    if(e.key==='ArrowDown'){e.preventDefault();pick=Math.min(pick+1,hits.length-1);paletteDraw();}
    else if(e.key==='ArrowUp'){e.preventDefault();pick=Math.max(pick-1,0);paletteDraw();}
    else if(e.key==='Enter'){e.preventDefault();if(hits[pick]){location.hash='#/'+hits[pick].view;palette.close();}}
  });
  palette.addEventListener('click',e=>{if(e.target===palette)palette.close();});
  document.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'&&!e.altKey){e.preventDefault();paletteOpen();}
  });
  if(/Mac|iPhone|iPad/.test(navigator.platform||''))document.querySelector('.search-btn kbd').textContent='⌘K';

  // Collapsible icon rail, remembered in this browser.
  const rail=$('rail-toggle');
  function railSet(c){document.body.classList.toggle('rail',c);rail.setAttribute('aria-pressed',String(c));rail.setAttribute('aria-label',c?'Expand sidebar':'Collapse sidebar');
    try{localStorage.setItem('qr-rail',c?'1':'0');}catch(_e){/* not remembered */}}
  rail.addEventListener('click',()=>railSet(!document.body.classList.contains('rail')));
  try{if(localStorage.getItem('qr-rail')==='1')railSet(true);}catch(_e){/* default: expanded */}

  // Status messages appear as a toast once signed in, then fade (errors stay longer).
  let toastTimer=null;
  new MutationObserver(()=>{
    const s=$('status');if(!document.body.classList.contains('signed-in'))return;
    s.classList.add('show');clearTimeout(toastTimer);
    const error=/denied|invalid|failed|refused|unavailable|error|exceeds|choose|required/i.test(s.textContent);
    toastTimer=setTimeout(()=>s.classList.remove('show'),error?9000:4500);
  }).observe($('status'),{childList:true,characterData:true,subtree:true});

  layout();route();
})();
