'use strict';
// Cinematic scene pack for flagship films. Same contract as scenes.js: draw(b, t, marks, dur) is a pure
// function of time; marks[i] is when narration sentence i starts. Enabled with "theme": "cine".
(function(){
  const {el,show,seg,ease,clamp,svgLayer,wire,grow,tree,scenes}=window.QR;
  const stage=document.getElementById('stage');
  const rng=seed=>()=>{seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};
  const blurIn=(n,p,scale)=>{n.style.opacity=p;n.style.filter=p>=1?'':'blur('+((1-p)*14).toFixed(2)+'px)';n.style.transform='scale('+(1+(1-p)*(scale||0.05))+')';};
  const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
  const NS='http://www.w3.org/2000/svg';
  const path=(svg,d,attrs)=>{const p=document.createElementNS(NS,'path');p.setAttribute('d',d);p.setAttribute('fill','none');for(const k in attrs)p.setAttribute(k,attrs[k]);svg.append(p);return p;};

  // ---- persistent film overlay: letterbox, scanlines, vignette, grain, HUD ----
  const fx=document.createElement('div');fx.className='cine-fx';
  fx.innerHTML='<div class="scan"></div><div class="vig"></div><canvas width="480" height="270"></canvas><div class="bar top"></div><div class="bar bot"></div>';
  const hud=document.createElement('div');hud.className='hud';
  hud.innerHTML='<div class="corner tl"></div><div class="corner tr"></div><div class="corner bl"></div><div class="corner br"></div>'+
    '<div class="lab" style="left:96px;top:38px">QUALITYRAG // EVIDENCE ENGINE</div><div class="lab tf" style="right:96px;top:38px"></div>'+
    '<div class="lab clock" style="left:96px;bottom:36px"></div><div class="lab" style="right:96px;bottom:36px"><span class="rec"></span>TRAINING FRAME</div>';
  const grainCtx=fx.querySelector('canvas').getContext('2d');const grainImg=grainCtx.createImageData(480,270);
  let frameNo=0;
  const ensure=()=>{if(!fx.isConnected){stage.append(fx);stage.append(hud);}};

  window.QR.after=function(name,t,marks,dur){
    const cine=stage.classList.contains('cine');
    fx.style.display=hud.style.display=cine?'':'none';
    if(!cine)return;ensure();
    const sc=scenes[name];
    hud.querySelector('.tf').textContent=sc.tf?('TF '+sc.tf[0]+' · '+sc.tf[1]).toUpperCase():'';
    hud.querySelector('.clock').textContent='T+'+String(Math.floor(t/60)).padStart(2,'0')+':'+(t%60).toFixed(2).padStart(5,'0');
    hud.style.opacity=sc.tf?Math.min(1,t/0.6):0;
    // Static grain: a texture, not per-frame noise (per-frame noise multiplies the file size by ~10).
    if(!frameNo++){const r=rng(7919),d=grainImg.data;for(let i=0;i<d.length;i+=4){const v=r()*255;d[i]=d[i+1]=d[i+2]=v;d[i+3]=255;}grainCtx.putImageData(grainImg,0,0);}
    const sceneEl=document.getElementById('scene');
    sceneEl.style.opacity=dur?Math.min(1,t/0.35,Math.max(0,(dur-t)/0.35)):1;
  };

  const title=(kicker,text,top)=>{const n=el('abs','<div class="cine-kicker">'+kicker+'</div><div class="cine-title" style="font-size:62px;margin-top:10px">'+text+'</div>',{left:'120px',top:(top||140)+'px'});return n;};

  // ---------- 00 · cold open ----------
  scenes.cold_open={build(){
    const b={};
    const c=document.createElement('canvas');c.width=1920;c.height=1080;c.style.position='absolute';c.style.inset='0';document.getElementById('scene').append(c);
    b.ctx=c.getContext('2d');const r=rng(42);
    b.docs=Array.from({length:900},()=>({x:80+r()*1760,y:110+r()*860,ph:r()*6.28,s:0.6+r()*0.8}));
    b.l=[['85,000 documents.','#F3F6FA'],['One question.','#F3F6FA'],['An answer that sounds certain.','#F5C46B']].map((x,i)=>el('abs cine-title',x[0],{left:'0',width:'1920px',textAlign:'center',top:(330+i*130)+'px',fontSize:'86px',color:x[1]}));
    b.beam=el('abs','',{top:'96px',height:'888px',width:'6px',background:'linear-gradient(180deg,transparent,#57E0CC,transparent)',boxShadow:'0 0 40px #57E0CC'});
    return b;
  },draw(b,t,m){
    const ctx=b.ctx;ctx.clearRect(0,0,1920,1080);
    const bx=-100+(t-m[1])/1.6*2100;b.beam.style.left=bx+'px';b.beam.style.opacity=(t>m[1]&&t<m[1]+1.6)?1:0;
    const settle=seg(t,m[2],1.2);
    for(const d of b.docs){
      const near=Math.max(0,1-Math.abs(d.x-bx)/120)*(t>m[1]&&t<m[1]+1.6?1:0);
      const a=(0.10+0.10*Math.sin(t*1.3+d.ph))*seg(t,0,1.2)+near*0.8;
      const x=d.x+(960-d.x)*settle*0.18,y=d.y+(540-d.y)*settle*0.18;
      ctx.fillStyle=near>0.05?'rgba(87,224,204,'+a+')':'rgba(200,210,225,'+a+')';ctx.fillRect(x,y,5*d.s,7*d.s);
    }
    b.l.forEach((n,i)=>blurIn(n,seg(t,m[i],0.8)));
  }};

  // ---------- 01 · the deceptive witness ----------
  scenes.witness={tf:['01','The deceptive witness'],build(){
    const b={};
    b.title=title('Training frame 01','The deceptive witness');
    b.claim=el('holo','<div class="meta">CLAIM</div><div class="txt">On-call may restart the gateway.</div>',{left:'720px',top:'450px',width:'480px',padding:'22px 26px'});
    const W=[['ops-7.3 · handbook · PDF','May initiate automated recovery…',140,300],['ops-mirror-7.3 · handbook · HTML','Copied excerpt: may initiate…',140,560],
             ['INC-7421 · incident · HTML','Automated recovery reduced downtime.',1380,300],['runbook · rev 2024 · DOCX','Restart once upstream stabilizes.',1380,560]];
    b.w=W.map(x=>el('holo','<div class="meta">'+x[0]+'</div><div class="txt" style="font-size:24px">'+x[1]+'</div>',{left:x[2]+'px',top:x[3]+'px',width:'400px',padding:'18px 22px'}));
    b.origin=el('holo','<div class="meta" style="color:#A99BFF">ORIGIN</div><div class="txt" style="font-size:24px">one document · ops-handbook</div>',{left:'140px',top:'800px',width:'400px',padding:'14px 22px',borderColor:'rgba(169,155,255,.6)'});
    const s=svgLayer();
    b.wires=[wire(s,'M540 360 C630 360 630 495 720 495'),wire(s,'M540 620 C630 620 630 525 720 525'),wire(s,'M1380 360 C1290 360 1290 495 1200 495'),wire(s,'M1380 620 C1290 620 1290 525 1200 525')];
    b.prov=[path(s,'M120 395 C80 395 80 830 140 830',{stroke:'#A99BFF','stroke-width':'2.5','stroke-dasharray':'8 8'}),path(s,'M120 655 C95 655 95 830 140 830',{stroke:'#A99BFF','stroke-width':'2.5','stroke-dasharray':'8 8'})];
    b.tags=[[140,440],[140,700],[1380,440],[1380,700]].map(p=>{const n=el('tag ok','supports',{left:p[0]+'px',top:p[1]+'px'});return n;});
    b.count=el('tag ok','1 independent source counts',{left:'822px',top:'590px'});
    b.beam=el('abs','',{top:'96px',height:'888px',width:'5px',background:'linear-gradient(180deg,transparent,#A99BFF,transparent)',boxShadow:'0 0 40px #A99BFF'});
    return b;
  },draw(b,t,m){
    blurIn(b.title,seg(t,m[0],0.8));blurIn(b.claim,seg(t,m[0]+0.6,0.6));
    b.w.forEach((n,i)=>show(n,seg(t,m[1]+0.2+i*0.25,0.5),0));
    b.wires.forEach((w,i)=>grow(w,seg(t,m[1]+0.6+i*0.25,0.6)));
    const state=[0,0,0,0];
    if(t>m[2]+1.6)state[1]=1;if(t>m[3]+0.6)state[2]=2;if(t>m[4]+0.8)state[3]=3;
    const looks=[['supports','ok'],['copy · counted once','dim'],['history ≠ authority','warn'],['superseded · too old','bad']];
    const col=['rgba(87,224,204,.6)','rgba(255,255,255,.18)','rgba(245,196,107,.75)','rgba(255,120,120,.75)'];
    b.tags.forEach((n,i)=>{const L=looks[state[i]];n.className='tag '+L[1];n.textContent=L[0];n.style.opacity=seg(t,m[1]+1.0+i*0.2,0.4);
      const holoCls=['holo','holo dim','holo warn','holo bad'][state[i]];b.w[i].className=holoCls;b.wires[i].setAttribute('stroke',col[state[i]]);
      if(state[i]===3||state[i]===2)b.wires[i].setAttribute('stroke-dasharray','1');});
    b.wires[1].style.strokeDasharray=state[1]?'0.02 0.02':'';
    const bx=60+(t-m[2])/1.3*900;b.beam.style.left=bx+'px';b.beam.style.opacity=(t>m[2]&&t<m[2]+1.3)?1:0;
    b.prov.forEach((p,i)=>{p.style.opacity=seg(t,m[2]+0.5+i*0.3,0.4);});show(b.origin,seg(t,m[2]+0.9,0.5),0);
    const g=t>m[2]+1.3&&t<m[2]+1.9;b.w[1].style.transform=g?'translate('+((Math.sin(t*90)*9)|0)+'px,'+((Math.cos(t*70)*3)|0)+'px)':'';
    b.w[1].style.filter=g?'drop-shadow(4px 0 0 rgba(255,80,120,.7)) drop-shadow(-4px 0 0 rgba(80,200,255,.7))':'';
    show(b.count,seg(t,m[4]+2.0,0.5),0);
  }};

  // ---------- 02 · the law (PackSpec) ----------
  const SPEC='{\n  "id": "eu-payments-screening-recovery",\n  "version": "1.0",\n  "requirements": [\n    {"id": "recovery-procedure",\n     "min_independent_sources": 1},\n    {"id": "eu-screening-control",\n     "min_independent_sources": 1,\n     "max_age_seconds": 31536000},\n    {"id": "approval-or-exception",\n     "min_independent_sources": 1}\n  ]\n}';
  const colour=s=>esc(s).replace(/("[^"\n]*")(\s*:)/g,'<span class="k">$1</span>$2').replace(/(:\s*)("[^"\n]*"?)/g,'$1<span class="s">$2</span>').replace(/(:\s*)(\d+)/g,'$1<span class="n">$2</span>');
  scenes.packspec={tf:['02','The law'],build(){
    const b={};
    b.title=title('Training frame 02 · PackSpec','The law');
    b.code=el('holo','<div class="meta">packspec.json · versioned</div><div class="code" style="font-size:23px;margin-top:12px"></div>',{left:'120px',top:'270px',width:'900px',height:'540px',padding:'22px 28px'});
    b.pre=b.code.querySelector('.code');
    const lanes=[['recovery-procedure','≥ 1 independent source'],['eu-screening-control','≥ 1 independent · ≤ 365 days'],['approval-or-exception','≥ 1 independent source']];
    b.lanes=lanes.map((x,i)=>el('holo','<div class="meta">REQUIREMENT</div><div class="txt" style="font-size:25px">'+x[0]+'<span style="float:right;font:18px var(--mono);color:#57E0CC;margin-top:6px">'+x[1]+'</span></div>',{left:'1120px',top:(290+i*120)+'px',width:'690px',padding:'16px 22px'}));
    const s=svgLayer();b.lw=[0,1,2].map(i=>wire(s,'M1020 '+(420+i*40)+' C1070 '+(420+i*40)+' 1070 '+(335+i*120)+' 1120 '+(335+i*120)));
    const langs=['Python','Java','TypeScript','Kotlin','Go','Rust','C#','Swift','Ruby','PHP'];
    b.langs=langs.map((l,i)=>el('tag dim',l,{left:(1120+(i%5)*140)+'px',top:(670+Math.floor(i/5)*52)+'px',fontSize:'16px'}));
    b.nollm=el('abs cine-title','No language model decides.',{left:'120px',top:'850px',fontSize:'46px',color:'#57E0CC'});
    return b;
  },draw(b,t,m){
    blurIn(b.title,seg(t,m[0],0.8));show(b.code,seg(t,m[0]+0.5,0.6),0);
    const n=Math.floor(clamp((t-m[1])/4.6)*SPEC.length);b.pre.innerHTML=colour(SPEC.slice(0,n))+(n<SPEC.length&&t>m[1]?'<span class="cursor" style="height:24px"></span>':'');
    b.lanes.forEach((x,i)=>blurIn(x,seg(t,m[1]+1.6+i*1.1,0.6)));b.lw.forEach((w,i)=>grow(w,seg(t,m[1]+1.8+i*1.1,0.6)));
    b.langs.forEach((x,i)=>{x.style.opacity=seg(t,m[2]+0.3+i*0.12,0.3);x.className='tag '+(t>m[2]+0.3+i*0.12+0.3?'ok':'dim');});
    blurIn(b.nollm,seg(t,m[3],0.7));
  }};

  // ---------- 03 · three verdicts ----------
  scenes.verdicts={tf:['03','Three verdicts'],build(){
    const b={};
    b.title=title('Training frame 03','Three verdicts');
    const V=[['ADMIT','#57E0CC'],['INCONCLUSIVE','#F5C46B'],['REFUSE','#FF8A8A']];
    b.v=V.map((v,i)=>{const n=el('verdict',v[0],{left:'0',width:'1920px',textAlign:'center',top:(250+i*170)+'px',color:v[1],textShadow:'0 0 40px '+v[1]+'66'});return n;});
    b.flare=V.map((v,i)=>el('abs','',{left:'0',width:'1920px',top:(318+i*170)+'px',height:'4px',background:'linear-gradient(90deg,transparent,'+v[1]+',transparent)'}));
    b.gap=el('holo warn','<div class="meta" style="color:#F5C46B">Wgap · answer withheld</div><div class="txt" style="font-size:26px">approval-or-exception · 0 of 1 independent sources</div>',{left:'560px',top:'800px',width:'800px',padding:'16px 24px',textAlign:'center'});
    b.fine=el('abs','<span style="color:#57E0CC">ADMIT</span> = the declared checks passed &nbsp;·&nbsp; <span style="color:#F5C46B">not</span> proof the source is true',{left:'0',width:'1920px',textAlign:'center',top:'820px',fontSize:'32px',color:'#C4CAD4'});
    return b;
  },draw(b,t,m){
    blurIn(b.title,seg(t,m[0],0.8));
    const on=b.v.map((n,i)=>seg(t,m[i+1],0.5));
    let focus=[1,1,1];if(t>m[4])focus=[0.25,1,0.25];if(t>m[5])focus=[1,0.35,0.35];
    b.v.forEach((n,i)=>{blurIn(n,on[i],0.12);n.style.opacity=on[i]*focus[i];});
    b.flare.forEach((f,i)=>{const p=t-m[i+1];f.style.opacity=p>0&&p<1.2?Math.sin(Math.PI*p/1.2):0;f.style.transform='scaleX('+(0.3+clamp(p/0.8))+')';});
    const g=seg(t,m[4]+0.4,0.5)*(1-seg(t,m[5]-0.2,0.4));show(b.gap,g,0);blurIn(b.fine,seg(t,m[5]+0.2,0.6));
  }};

  // ---------- 05 · the semantic garden ----------
  scenes.garden={tf:['05','The Semantic Garden'],build(){
    const b={};
    b.title=title('Training frame 05','The Semantic Garden');
    const s=svgLayer();b.svg=s;const r=rng(7);
    b.br=[];
    const grow1=(x,y,ang,len,depth,born,parent)=>{
      const x2=x+Math.cos(ang)*len,y2=y+Math.sin(ang)*len;
      const p=path(s,'M'+x.toFixed(1)+' '+y.toFixed(1)+' L'+x2.toFixed(1)+' '+y2.toFixed(1),{stroke:'rgba(87,224,204,.75)','stroke-width':String(Math.max(1.4,7-depth*1.05)),'stroke-linecap':'round',pathLength:'1','stroke-dasharray':'1','stroke-dashoffset':'1'});
      const node={p,x,y,x2,y2,depth,born,dur:0.42,parent,kids:[]};b.br.push(node);
      if(depth<6){const k=depth<2?2:(r()<0.3?3:2);
        for(let i=0;i<k;i++){const spread=(k===2?(i?1:-1):(i-1))*(0.32+r()*0.22);
          node.kids.push(grow1(x2,y2,ang+spread+(r()-0.5)*0.12,len*(0.72+r()*0.08),depth+1,born+0.42+r()*0.25,node));}}
      return node;};
    b.root=grow1(800,960,-Math.PI/2,150,0,0,null);
    const leaves=b.br.filter(n=>!n.kids.length);
    b.pick=i=>leaves[Math.floor(i*leaves.length)];
    b.challenge=b.pick(0.15);b.tested=b.pick(0.62);b.pruned=b.pick(0.88);b.newTip=b.pick(0.4);
    const a=b.pick(0.3),c=b.pick(0.52);b.synA=a;b.synC=c;
    const mx=(a.x2+c.x2)/2,my=Math.min(a.y2,c.y2)-90;
    b.syn=path(s,'M'+a.x2+' '+a.y2+' Q'+mx+' '+(my+40)+' '+mx+' '+my+' Q'+mx+' '+(my+40)+' '+c.x2+' '+c.y2,{stroke:'#A99BFF','stroke-width':'3.5',pathLength:'1','stroke-dasharray':'1','stroke-dashoffset':'1'});
    b.synNode=el('abs','',{left:(mx-9)+'px',top:(my-9)+'px',width:'18px',height:'18px',borderRadius:'99px',background:'#A99BFF',boxShadow:'0 0 24px #A99BFF'});
    b.sprout=path(s,'M'+b.newTip.x2+' '+b.newTip.y2+' l'+(-28)+' '+(-62),{stroke:'#EDEFF3','stroke-width':'2.4','stroke-linecap':'round',pathLength:'1','stroke-dasharray':'1','stroke-dashoffset':'1'});
    const tag=(txt,cls,n,dx,dy)=>el('tag '+cls,txt,{left:(n.x2+(dx||14))+'px',top:(n.y2+(dy||-14))+'px'});
    b.tags={propose:tag('propose','dim',{x2:b.newTip.x2-28,y2:b.newTip.y2-62},-120,-40),challenge:tag('challenge','warn',b.challenge,-150,-40),test:tag('test','ok',b.tested,16,-40),
      synthesize:el('tag','synthesize',{left:(mx+18)+'px',top:(my-40)+'px',background:'#A99BFF',color:'#0B0820'}),prune:tag('prune','dim',b.pruned,16,-40),reopen:tag('reopen','ok',b.pruned,16,-40)};
    b.agents=Array.from({length:7},(_,i)=>({el:el('abs','',{width:'10px',height:'10px',borderRadius:'99px',background:'#EDEFF3',boxShadow:'0 0 14px #57E0CC'}),leaf:leaves[Math.floor(rng(100+i)()*leaves.length)],off:i*0.55}));
    b.log=el('holo','<div class="meta">APPEND-ONLY LEDGER</div><div class="code" style="font-size:18px;margin-top:10px;line-height:1.9"></div>',{left:'1440px',top:'260px',width:'390px',padding:'18px 22px'});
    b.logPre=b.log.querySelector('.code');
    return b;
  },draw(b,t,m){
    blurIn(b.title,seg(t,m[0],0.8));
    const t0=m[1]-0.2;
    for(const n of b.br){grow(n.p,seg(t,t0+n.born,n.dur));}
    const ev=[['propose',m[2]+1.2],['challenge',m[2]+1.8],['test',m[2]+2.4],['synthesize',m[2]+2.9],['prune',m[3]+0.2],['reopen',m[4]+1.0]];
    const at=k=>ev.find(e=>e[0]===k)[1];
    grow(b.sprout,seg(t,at('propose'),0.5));
    const ch=t>at('challenge');b.challenge.p.setAttribute('stroke',ch?'#F5C46B':'rgba(87,224,204,.75)');
    const ts=t>at('test');b.tested.p.setAttribute('stroke',ts?'#9FFFF0':'rgba(87,224,204,.75)');b.tested.p.style.filter=ts?'drop-shadow(0 0 8px #57E0CC)':'';
    grow(b.syn,seg(t,at('synthesize'),0.8));b.synNode.style.opacity=seg(t,at('synthesize')+0.6,0.3);
    const pr=t>at('prune')&&t<at('reopen');const ro=t>=at('reopen');
    b.pruned.p.setAttribute('stroke',pr?'rgba(255,255,255,.28)':(ro?'#9FFFF0':'rgba(87,224,204,.75)'));
    if(pr){b.pruned.p.setAttribute('stroke-dasharray','0.06 0.05');b.pruned.p.setAttribute('stroke-dashoffset','0');}
    else if(ro){b.pruned.p.setAttribute('stroke-dasharray','1');b.pruned.p.style.filter='drop-shadow(0 0 10px #57E0CC)';}
    for(const [k,s0] of ev){const n=b.tags[k];let o=seg(t,s0,0.3);if(k==='prune')o*=1-seg(t,at('reopen'),0.3);n.style.opacity=o;}
    b.agents.forEach(a=>{const chain=[];let n=a.leaf;while(n){chain.unshift(n);n=n.parent;}
      const T=(t-m[2]+a.off)/3.2;if(t<m[2]||T<0){a.el.style.opacity=0;return;}
      const f=T%1,k=f*chain.length,i=Math.min(chain.length-1,Math.floor(k)),q=k-i,c=chain[i];
      a.el.style.opacity=Math.sin(Math.PI*f)*0.95;a.el.style.left=(c.x+(c.x2-c.x)*q-5)+'px';a.el.style.top=(c.y+(c.y2-c.y)*q-5)+'px';});
    show(b.log,seg(t,m[2]+0.6,0.5),0);
    const lines=[['PROPOSE','exception-scope'],['CHALLENGE','exception-scope'],['TEST','ledger run 17'],['SYNTHESIZE','scope + authority'],['PRUNE','keyword-only'],['REOPEN','keyword-only']];
    b.logPre.innerHTML=lines.map((l,i)=>t>ev[i][1]?'<span class="k">'+l[0].padEnd(11)+'</span>'+esc(l[1]):'').filter(Boolean).join('\n');
  }};

  // ---------- 06 · evolution ----------
  scenes.evolve={tf:['06','Evolution'],build(){
    const b={};
    b.title=title('Training frame 06','Evolution');
    const meters=['distinctions preserved','representation cost','activation cost'];
    const card=(k,left,cls)=>el('holo '+(cls||''),'<div class="meta">'+k+'</div>'+meters.map(x=>'<div style="margin-top:18px;font-size:22px;color:#C4CAD4">'+x+'<div class="m" style="height:8px;border-radius:9px;background:rgba(255,255,255,.08);margin-top:8px;overflow:hidden"><div style="height:100%;width:0;background:#57E0CC"></div></div></div>').join(''),{left:left+'px',top:'360px',width:'560px',padding:'24px 28px'});
    b.champ=card('CHAMPION',240);b.cand=card('CANDIDATE',1120);
    b.vs=el('abs cine-title','VS',{left:'900px',width:'120px',textAlign:'center',top:'500px',fontSize:'54px',color:'#8E97A5'});
    b.fam=['family 17','family 18','family 19'].map((f,i)=>el('tag dim',f,{left:(735+i*160)+'px',top:'250px'}));
    b.same=el('tag ok','same PackSpec',{left:'880px',top:'300px'});
    b.res=[el('tag dim','kept · counterexample',{left:'240px',top:'760px'}),el('tag ok','promoted',{left:'1120px',top:'760px'})];
    b.vals=[[0.62,0.55,0.48],[0.74,0.43,0.40]];
    const R=290,cx=960,cy=545,st=['Find failure','Investigate','Propose','Test','Retain','Promote · reopen'];
    b.cx=cx;b.cy=cy;b.R=R;
    const s=svgLayer();b.ring=path(s,'M'+(cx)+' '+(cy-R)+' A'+R+' '+R+' 0 1 1 '+(cx-0.1)+' '+(cy-R),{stroke:'rgba(87,224,204,.35)','stroke-width':'2.5',pathLength:'1','stroke-dasharray':'1','stroke-dashoffset':'1'});
    b.nodes=st.map((x,i)=>{const a=-Math.PI/2+i*Math.PI/3,X=cx+Math.cos(a)*R,Y=cy+Math.sin(a)*R;
      const dot=el('abs','',{left:(X-11)+'px',top:(Y-11)+'px',width:'22px',height:'22px',borderRadius:'99px',border:'2px solid #57E0CC',background:'#030508'});
      const lab=el('abs',x,{left:(X+(Math.cos(a)>0.2?26:Math.cos(a)<-0.2?-26:0))+'px',top:(Y-16+(Math.sin(a)<-0.9?-40:Math.sin(a)>0.9?40:0))+'px',fontSize:'28px',fontWeight:'650',color:'#EDEFF3',whiteSpace:'nowrap',transform:Math.cos(a)<-0.2?'translateX(-100%)':(Math.abs(Math.cos(a))<=0.2?'translateX(-50%)':'')});
      return {dot,lab};});
    b.spark=el('abs','',{width:'16px',height:'16px',borderRadius:'99px',background:'#EDEFF3',boxShadow:'0 0 26px #57E0CC'});
    return b;
  },draw(b,t,m){
    blurIn(b.title,seg(t,m[0],0.8));
    const A=1-seg(t,m[2]-0.1,0.5);
    [b.champ,b.cand].forEach((c,j)=>{show(c,seg(t,m[0]+0.3+j*0.2,0.5)*A,0);
      [...c.querySelectorAll('.m > div')].forEach((bar,i)=>{bar.style.width=(100*b.vals[j][i]*ease((t-m[0]-1.4-i*0.3)/1.4))+'%';});});
    b.vs.style.opacity=seg(t,m[0]+0.6,0.4)*A;
    b.fam.forEach((f,i)=>{const p=seg(t,m[0]+0.8+i*0.35,0.5);f.style.opacity=p*A;f.style.transform='translateY('+(1-p)*-30+'px)';});
    b.same.style.opacity=seg(t,m[0]+2.6,0.4)*A;
    b.res.forEach((r,i)=>{r.style.opacity=seg(t,m[1]+(i?0.2:1.6),0.4)*A;});
    b.cand.className='holo'+(t>m[1]+0.2?' ':' dim');b.champ.className='holo'+(t>m[1]+1.6?' dim':'');
    const B=seg(t,m[2]+0.1,0.6);grow(b.ring,seg(t,m[2]+0.2,1.0));
    b.nodes.forEach((n,i)=>{const on=t>m[2]+1.3+i*0.72;n.dot.style.opacity=B;n.lab.style.opacity=B*(on?1:0.35);n.dot.style.background=on?'#57E0CC':'#030508';n.dot.style.boxShadow=on?'0 0 18px #57E0CC':'none';});
    const a=-Math.PI/2+((t-m[2]-1.3)/0.72)*Math.PI/3;b.spark.style.opacity=t>m[2]+1.3?B:0;
    b.spark.style.left=(b.cx+Math.cos(a)*b.R-8)+'px';b.spark.style.top=(b.cy+Math.sin(a)*b.R-8)+'px';
  }};

  // ---------- finale ----------
  scenes.finale={build(){
    const b={};
    const c=document.createElement('canvas');c.width=1920;c.height=1080;c.style.position='absolute';c.style.inset='0';document.getElementById('scene').append(c);
    b.ctx=c.getContext('2d');const r=rng(9);
    b.p=Array.from({length:520},()=>{const a=r()*6.283,d=600+r()*700;return {x0:960+Math.cos(a)*d,y0:540+Math.sin(a)*d,x1:620+r()*680,y1:400+r()*130,ph:r()};});
    b.tag=el('abs cine-title','Evidence before answers.',{left:'0',width:'1920px',textAlign:'center',top:'460px',fontSize:'90px'});
    b.logo=el('abs',tree(110),{left:'905px',top:'200px'});
    b.word=el('abs cine-title','QualityRag',{left:'0',width:'1920px',textAlign:'center',top:'350px',fontSize:'128px'});
    b.links=el('abs mono','github.com/cyrillesaxo/QualityRag &nbsp; · &nbsp; QualityRag Academy',{left:'0',width:'1920px',textAlign:'center',top:'790px',fontSize:'28px',color:'#C4CAD4'});
    return b;
  },draw(b,t,m){
    const ctx=b.ctx;ctx.clearRect(0,0,1920,1080);
    const k=ease((t-0.2)/(m[1]-0.2));const fade=1-seg(t,m[1]+0.4,0.8);
    for(const p of b.p){const x=p.x0+(p.x1-p.x0)*k,y=p.y0+(p.y1-p.y0)*k;ctx.fillStyle='rgba(87,224,204,'+(0.55*fade*(0.4+0.6*Math.sin(6.28*(p.ph+t*0.4))**2))+')';ctx.fillRect(x,y,3,3);}
    const mv=seg(t,m[1],0.9);
    blurIn(b.tag,seg(t,m[0],0.9));b.tag.style.top=(460+150*mv)+'px';b.tag.style.fontSize=(90-44*mv)+'px';b.tag.style.color=mv>0.5?'#57E0CC':'#F3F6FA';
    b.logo.querySelector('.draw').style.strokeDashoffset=String(1-seg(t,m[1]+0.2,1.2));
    blurIn(b.word,seg(t,m[1]+0.3,0.9),0.1);blurIn(b.links,seg(t,m[1]+1.6,0.7));
  }};
})();
