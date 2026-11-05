'use strict';
// Deterministic training animations: window.render(scene, t, marks) draws the frame at time t
// (seconds). marks[i] is when narration sentence i starts, so motion follows the voice.
(function(){
  const root=document.getElementById('scene');
  let built=null;
  const clamp=x=>Math.max(0,Math.min(1,x));
  const ease=x=>{x=clamp(x);return x*x*(3-2*x);};
  const seg=(t,a,d)=>ease((t-a)/(d||0.6));
  const el=(cls,html,style)=>{const n=document.createElement('div');n.className=cls;if(html!==undefined)n.innerHTML=html;if(style)Object.assign(n.style,style);root.append(n);return n;};
  const show=(n,p,dy)=>{n.style.opacity=p;n.style.transform='translateY('+((1-p)*(dy===undefined?24:dy))+'px)';};
  const svgLayer=()=>{const s=document.createElementNS('http://www.w3.org/2000/svg','svg');s.setAttribute('width','1920');s.setAttribute('height','1080');s.style.position='absolute';s.style.left='0';s.style.top='0';root.prepend(s);return s;};
  const wire=(svg,d,color)=>{const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',d);p.setAttribute('fill','none');p.setAttribute('stroke',color||'rgba(87,224,204,.55)');p.setAttribute('stroke-width','3');p.setAttribute('stroke-linecap','round');p.setAttribute('pathLength','1');p.setAttribute('stroke-dasharray','1');p.setAttribute('stroke-dashoffset','1');svg.append(p);return p;};
  const grow=(p,x)=>p.setAttribute('stroke-dashoffset',String(1-x));
  const CHECK='<svg viewBox="0 0 20 20"><path d="M4 10.5 8 14.5 16 5.5" fill="none" stroke="#57E0CC" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const tree=(size)=>'<svg viewBox="0 0 22 22" width="'+size+'" height="'+size+'"><path class="draw" d="M11 20V11M11 11 5 4M11 11l6-7M11 14 7 9M11 14l4-5" fill="none" stroke="#57E0CC" stroke-width="1.6" stroke-linecap="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg>';

  const scenes={
    title:{build(){
      return {logo:el('abs',tree(150),{left:'885px',top:'250px'}),
        h:el('abs h1','QualityRag 101',{left:'0',width:'1920px',top:'440px',textAlign:'center'}),
        s:el('abs body','Episode 1 · Getting started',{left:'0',width:'1920px',top:'580px',textAlign:'center',fontSize:'40px',color:'#57E0CC',fontWeight:'600'}),
        d:el('abs body','Check whether your evidence supports an answer, before anyone relies on it.',{left:'0',width:'1920px',top:'660px',textAlign:'center'})};
    },draw(b,t,m){
      b.logo.querySelector('.draw').style.strokeDashoffset=String(1-ease(t/1.6));
      show(b.h,seg(t,0.5,0.8));show(b.s,seg(t,1.0,0.7));show(b.d,seg(t,m[1]||2,0.8));
    }},

    rag:{build(){
      const b={};
      b.q=el('card','<div class="kicker">Question</div><div class="body" style="color:#EDEFF3;margin-top:10px">Can on-call automatically restore the EU payments gateway after a sanctions-screening failure?</div>',{left:'110px',top:'200px',width:'560px',padding:'28px 32px'});
      b.search=el('abs chip','Search',{left:'760px',top:'300px'});
      const ps=[['ops-handbook · rev 2026','On-call staff may initiate automated recovery after a dependency timeout.'],
        ['legacy-runbook · rev 2024','Restart the gateway once upstream connectivity stabilizes.'],
        ['incident-7421 · rev 2025','During a prior outage, automated recovery reduced downtime.']];
      b.ps=ps.map((p,i)=>el('card passage','<div class="meta">'+p[0]+'</div><div class="text">'+p[1]+'</div>',{left:'1000px',top:(180+i*190)+'px'}));
      b.llm=el('card','<div class="kicker" style="text-align:center">Language model</div>',{left:'1600px',top:'330px',width:'230px',height:'140px',display:'flex',alignItems:'center',justifyContent:'center'});
      b.ans=el('card','<div class="kicker">Answer</div><div class="body" style="color:#EDEFF3;margin-top:10px">Yes. Restart the gateway once upstream connectivity stabilizes.</div>',{left:'1240px',top:'720px',width:'600px',padding:'26px 30px'});
      b.warn=el('abs chip bad','Built on a 2024 runbook that predates current controls',{left:'420px',top:'770px'});
      const s=svgLayer();
      b.w1=wire(s,'M670 312 L760 326');b.w1b=wire(s,'M890 326 C940 326 950 250 1000 250');b.w1c=wire(s,'M890 326 C950 326 950 440 1000 440');b.w1d=wire(s,'M890 326 C960 326 950 630 1000 630');
      b.w2=[250,440,630].map(y=>wire(s,'M1520 '+y+' C1560 '+y+' 1560 400 1600 400'));
      b.w3=wire(s,'M1715 470 L1715 720');
      return b;
    },draw(b,t,m){
      show(b.q,seg(t,m[0],0.6));show(b.search,seg(t,m[1],0.5),0);
      b.ps.forEach((p,i)=>show(p,seg(t,m[1]+0.4+i*0.35,0.5)));
      grow(b.w1,seg(t,m[1]-0.1,0.4));[b.w1b,b.w1c,b.w1d].forEach((w,i)=>grow(w,seg(t,m[1]+0.2+i*0.35,0.5)));
      b.w2.forEach((w,i)=>grow(w,seg(t,m[1]+1.4+i*0.12,0.5)));grow(b.w3,seg(t,m[1]+2.3,0.4));
      show(b.llm,seg(t,m[1]+1.6,0.5),0);show(b.ans,seg(t,m[1]+2.6,0.6));
      const w=seg(t,m[2]+0.2,0.5);show(b.warn,w,0);
      b.ps[1].style.borderColor=w>0.5?'rgba(255,154,154,.7)':'';b.ans.style.borderColor=w>0.5?'rgba(255,154,154,.7)':'';
    }},

    gate:{build(){
      const b={};
      b.policy=el('card','<div class="kicker">Your policy</div><div class="body" style="margin-top:12px;color:#EDEFF3">recovery procedure · EU screening control · approval or exception</div>',{left:'110px',top:'170px',width:'1700px',padding:'24px 32px'});
      b.ps=['ops-handbook','eu-control-annex','regional-change-memo'].map((o,i)=>el('card','<div class="mono" style="font-size:24px;color:#C4CAD4">'+o+'</div>',{left:'110px',top:(380+i*120)+'px',width:'420px',padding:'26px 28px'}));
      const rows=['Linked to a requirement','Independent sources counted','Fresh enough (max age)','Nothing contradicts it'];
      b.gate=el('card','<div class="kicker" style="margin-bottom:10px">The check</div>'+rows.map(r=>'<div class="tick"><span class="box">'+CHECK+'</span><span>'+r+'</span></div>').join(''),{left:'640px',top:'350px',width:'620px',padding:'28px 34px'});
      b.ticks=[...b.gate.querySelectorAll('.box svg')];
      b.v=[['Supported','ok'],['Not enough evidence','warn'],['Contradicted','bad']].map((v,i)=>el('abs chip '+v[1],v[0],{left:'1380px',top:(400+i*110)+'px',fontSize:'30px',padding:'14px 26px'}));
      b.flow=[0,1,2].map(()=>el('abs','',{width:'18px',height:'18px',borderRadius:'999px',background:'#57E0CC',boxShadow:'0 0 18px #57E0CC'}));
      const s=svgLayer();
      b.win=[420,540,660].map(y=>wire(s,'M530 '+y+' C585 '+y+' 585 525 640 525'));
      b.wout=[433,543,653].map(y=>wire(s,'M1260 525 C1320 525 1320 '+y+' 1380 '+y,'rgba(255,255,255,.22)'));
      return b;
    },draw(b,t,m){
      show(b.gate,seg(t,m[0],0.6));show(b.policy,seg(t,m[1],0.6));
      b.ps.forEach((p,i)=>show(p,seg(t,m[2]-0.2+i*0.2,0.5)));
      b.ticks.forEach((s,i)=>{s.style.opacity=seg(t,m[2]+0.5+i*0.9,0.4);});
      b.flow.forEach((d,i)=>{const p=((t-m[2]-i*0.5)%2.2)/2.2;const on=t>m[2]&&t<m[3]+3;d.style.opacity=on&&p>0?Math.sin(Math.PI*p):0;
        const y0=[420,540,660][i];d.style.left=(521+p*110)+'px';d.style.top=(y0-9+(525-y0)*p)+'px';});
      b.win.forEach((w,i)=>grow(w,seg(t,m[2]+i*0.2,0.6)));b.wout.forEach((w,i)=>grow(w,seg(t,m[3]+0.1+i*0.5,0.5)));
      b.v.forEach((v,i)=>show(v,seg(t,m[3]+0.3+i*0.5,0.5),0));
      const hi=seg(t,m[3]+2.2,0.5);b.v[0].style.boxShadow='0 0 0 '+(6*hi)+'px rgba(87,224,204,.25)';
    }},

    copies:{build(){
      const b={};
      b.k=el('abs kicker','Two details',{left:'110px',top:'170px'});
      b.a=el('card passage','<div class="meta">ops-7.3 · ops-handbook · PDF</div><div class="text">On-call staff may initiate automated recovery after a dependency timeout.</div>',{left:'110px',top:'250px'});
      b.c=el('card passage','<div class="meta">ops-mirror-7.3 · ops-handbook · HTML</div><div class="text">Copied excerpt: on-call staff may initiate automated recovery…</div>',{left:'110px',top:'250px'});
      b.badge=el('abs chip ok','1 independent source · copy counted once',{left:'110px',top:'560px'});
      b.u=el('card passage','<div class="meta">annex-d-187 · eu-control-annex · Appendix D, p. 187</div><div class="text">Restoration requires compliance sign-off <span class="mark">unless</span> the documented emergency exception applies.</div>',{left:'1000px',top:'250px',width:'800px'});
      b.note=el('abs chip warn','Counted as support · the condition is for a person to read',{left:'1000px',top:'560px'});
      return b;
    },draw(b,t,m){
      show(b.k,seg(t,m[0],0.5));
      const a=seg(t,m[1],0.6);show(b.a,a);show(b.c,a);
      const merge=seg(t,m[1]+1.4,0.9);b.c.style.transform='translate('+(560*(1-merge)+16*merge)+'px,'+(40*(1-merge)+16*merge)+'px)';
      b.c.style.opacity=a;b.c.style.zIndex='0';b.a.style.zIndex='1';b.a.style.background='#141922';
      for(const n of b.c.children)n.style.opacity=1-merge;
      show(b.badge,seg(t,m[1]+2.4,0.5),0);
      show(b.u,seg(t,m[2],0.6));
      const mk=b.u.querySelector('.mark');const pulse=seg(t,m[2]+0.9,0.4);mk.style.boxShadow='0 0 0 '+(5*pulse)+'px rgba(245,166,35,.35)';
      show(b.note,seg(t,m[2]+1.6,0.5),0);
    }},

    setup:{build(){
      const b={};
      b.term=el('card term','<div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="mono" style="margin-left:14px;font-size:20px;color:#8E97A5">terminal</span></div><pre></pre>');
      b.pre=b.term.querySelector('pre');
      b.lines=[
        {at:1,cmd:'git clone https://github.com/cyrillesaxo/QualityRag.git && cd QualityRag'},
        {at:1,cmd:'pip install -r tools/activation_runtime/requirements.txt'},
        {at:2,cmd:'python -m tools.activation_runtime.bootstrap --root ~/qualityrag-local',out:'{…, "browser_token_file": "~/qualityrag-local/browser-token.txt", "mode": "LOCAL_RESEARCH_ONLY", …}'},
        {at:3,cmd:'python -m tools.activation_runtime.cli serve --root ~/qualityrag-local/state \\\n    --keys ~/qualityrag-local/public-keys.json --port 8769',out:'{"listening": "http://127.0.0.1:8769", "mode": "RESEARCH"}'}];
      b.open=el('abs chip ok','Open http://127.0.0.1:8769',{left:'210px',top:'850px',fontSize:'30px'});
      return b;
    },draw(b,t,m){
      show(b.term,seg(t,m[0],0.6));
      const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
      let html='',cursor=false;
      const starts={};b.lines.forEach(l=>{starts[l.at]=(starts[l.at]||0);});
      const order={};let sub={};
      b.lines.forEach((l,i)=>{sub[l.at]=(sub[l.at]||0);const st=m[l.at]+0.2+sub[l.at]*1.9;sub[l.at]++;
        const chars=Math.floor(clamp((t-st)/1.4)*l.cmd.length);if(t<st)return;
        html+='<span class="p">$ </span>'+esc(l.cmd.slice(0,chars));
        if(chars<l.cmd.length){cursor=true;html+='<span class="cursor"></span>\n';return;}
        html+='\n';if(l.out&&t>st+1.7)html+='<span class="o">'+esc(l.out)+'</span>\n';});
      if(!cursor)html+='<span class="p">$ </span>'+(Math.floor(t*2)%2?'<span class="cursor"></span>':'');
      b.pre.innerHTML=html;
      show(b.open,seg(t,m[3]+3.6,0.5),0);
    }},

    recap:{build(){
      const b={};
      b.k=el('abs kicker','In this episode',{left:'110px',top:'200px'});
      const items=['Installed QualityRag and created a local token','Signed in to the console','Checked an answer and read the result','Saw why the result changed when evidence was removed'];
      b.items=items.map((s,i)=>el('abs','<span class="tick" style="border:0"><span class="box">'+CHECK+'</span><span>'+s+'</span></span>',{left:'110px',top:(270+i*80)+'px'}));
      b.next=el('card','<div class="kicker">Next</div><div class="h2" style="margin-top:10px">Episode 2 · Fixing what Health finds</div>',{left:'110px',top:'640px',width:'1100px',padding:'30px 36px'});
      return b;
    },draw(b,t,m){
      show(b.k,seg(t,m[0],0.5));
      b.items.forEach((n,i)=>{show(n,seg(t,m[0]+0.3+i*0.6,0.5));n.querySelector('svg').style.opacity=seg(t,m[0]+0.6+i*0.6,0.3);});
      show(b.next,seg(t,m[1],0.7));
    }},
    // ---- homepage cut ----
    hook:{build(){
      const b={};
      b.h1=el('abs h2','Your RAG found the document.',{left:'110px',top:'230px'});
      b.h2=el('abs h2','But it missed the condition.',{left:'110px',top:'306px',color:'#F5C46B'});
      b.doc=el('card passage','<div class="meta">annex-d-187 · eu-control-annex · Appendix D, p. 187</div><div class="text">Restoration <span class="mk">requires compliance sign-off</span> <span class="mk">unless</span> the documented emergency exception applies.</div>',{left:'110px',top:'480px',width:'860px',padding:'28px 32px'});
      b.doc.querySelector('.text').style.fontSize='32px';
      b.found=el('abs chip ok','Retrieved',{left:'110px',top:'700px'});
      b.ans=el('card','<div class="kicker">Answer</div><div class="body" style="color:#EDEFF3;margin-top:10px;font-size:36px">Yes. Restart the gateway.</div>',{left:'1110px',top:'480px',width:'700px',padding:'28px 32px'});
      b.miss=el('abs chip bad','Sign-off requirement ignored',{left:'1110px',top:'700px'});
      const s=svgLayer();b.w=wire(s,'M970 560 L1110 560');
      return b;
    },draw(b,t,m){
      show(b.h1,seg(t,m[0],0.5));show(b.doc,seg(t,m[0]+0.3,0.6));show(b.found,seg(t,m[0]+1.0,0.4),0);
      grow(b.w,seg(t,m[0]+1.2,0.4));show(b.ans,seg(t,m[0]+1.5,0.5));
      const c=seg(t,m[1],0.5);show(b.h2,c);
      b.doc.querySelectorAll('.mk').forEach((k,i)=>{const p=seg(t,m[1]+0.4+i*0.5,0.4);k.style.background='rgba(245,166,35,'+(0.30*p)+')';k.style.color=p>0.5?'#FFD58A':'';k.style.borderRadius='5px';k.style.padding='0 4px';});
      show(b.miss,seg(t,m[1]+1.3,0.4),0);b.ans.style.borderColor=seg(t,m[1]+1.3,0.4)>0.5?'rgba(255,154,154,.7)':'';
    }},

    versus:{build(){
      const b={};
      b.lk=el('abs kicker','Conventional RAG',{left:'110px',top:'290px'});
      b.l=el('card','<div class="body" style="color:#EDEFF3;font-size:34px">Yes. Restart the gateway once upstream connectivity stabilizes.</div>',{left:'110px',top:'340px',width:'700px',padding:'30px 34px'});
      b.lc=el('abs chip','Answers anyway',{left:'110px',top:'530px'});
      b.rk=el('abs kicker','QualityRag',{left:'960px',top:'290px',color:'#57E0CC'});
      const reqs=[['recovery procedure','Supported','ok'],['EU screening control','Supported · “unless” flagged','warn'],['approval or exception','0 of 1 independent sources','bad']];
      b.reqs=reqs.map((r,i)=>el('card','<div style="display:flex;justify-content:space-between;align-items:center;gap:20px"><span class="body" style="color:#EDEFF3">'+r[0]+'</span><span class="chip '+r[2]+'" style="font-size:22px;padding:8px 16px">'+r[1]+'</span></div>',{left:'960px',top:(340+i*112)+'px',width:'850px',padding:'22px 28px'}));
      b.v=el('abs chip warn','Not enough evidence',{left:'960px',top:'710px',fontSize:'34px',padding:'16px 30px'});
      return b;
    },draw(b,t,m){
      show(b.lk,seg(t,m[0],0.4));show(b.l,seg(t,m[0]+0.2,0.5));show(b.lc,seg(t,m[0]+1.0,0.4),0);
      show(b.rk,seg(t,m[1],0.4));b.reqs.forEach((r,i)=>show(r,seg(t,m[1]+0.4+i*0.5,0.5)));
      const v=seg(t,m[2]+0.6,0.5);show(b.v,v,0);b.v.style.boxShadow='0 0 0 '+(6*v)+'px rgba(245,166,35,.2)';
    }},

    why:{build(){
      const b={};
      const tiles=[['Independent sources','Copies of one document count once.'],['Freshness','Evidence older than the policy allows is rejected.'],['Conditions','“unless” and “only” are flagged for a person.']];
      b.t=tiles.map((x,i)=>el('card','<div class="h2" style="font-size:40px">'+x[0]+'</div><div class="body" style="margin-top:14px">'+x[1]+'</div>',{left:(110+i*580)+'px',top:'300px',width:'540px',height:'260px',padding:'34px 36px'}));
      b.n=el('abs h2','Not the model’s confidence.',{left:'0',width:'1920px',textAlign:'center',top:'680px',color:'#57E0CC'});
      return b;
    },draw(b,t,m){
      b.t.forEach((x,i)=>show(x,seg(t,m[0]+i*1.1,0.5)));show(b.n,seg(t,m[0]+3.6,0.6));
    }},

    cta:{build(){
      const b={};
      b.logo=el('abs',tree(120),{left:'900px',top:'170px'});
      b.h=el('abs h1','QualityRag',{left:'0',width:'1920px',top:'320px',textAlign:'center'});
      b.s=el('abs body','Beyond relevant chunks. Toward evidence-governed answers.',{left:'0',width:'1920px',top:'450px',textAlign:'center',fontSize:'38px'});
      b.gh=el('card','<div class="kicker">Open source</div><div class="mono" style="font-size:30px;margin-top:10px;color:#EDEFF3">github.com/cyrillesaxo/QualityRag</div>',{left:'260px',top:'620px',width:'680px',padding:'28px 34px'});
      b.pl=el('card','<div class="kicker" style="color:#57E0CC">RAG reliability pilot</div><div class="mono" style="font-size:30px;margin-top:10px;color:#EDEFF3">DODO LLC · dodollc.net</div>',{left:'980px',top:'620px',width:'680px',padding:'28px 34px',borderColor:'rgba(87,224,204,.45)'});
      return b;
    },draw(b,t,m){
      b.logo.querySelector('.draw').style.strokeDashoffset=String(1-ease(t/1.4));
      show(b.h,seg(t,m[0],0.6));show(b.s,seg(t,m[0]+0.8,0.6));show(b.gh,seg(t,m[1],0.5));show(b.pl,seg(t,m[1]+1.2,0.5));
    }},
  };

  // Shared with additional scene packs (cine.js) loaded after this file.
  window.QR={root,el,show,seg,ease,clamp,svgLayer,wire,grow,tree,CHECK,scenes};

  window.render=function(name,t,marks,episode,dur){
    if(episode)document.getElementById('epmark').textContent=episode;
    if(!built||built.name!==name){root.replaceChildren();built={name,b:scenes[name].build()};}
    scenes[name].draw(built.b,t,marks);
    if(window.QR.after)window.QR.after(name,t,marks,dur);
    return true;
  };
  window.sceneNames=Object.keys(scenes);
})();
