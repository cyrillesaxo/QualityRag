'use strict';
// Data-driven cinematic templates. An episode scene says {"template": "board", "data": {...}} and is written
// entirely in script.json. Times are mark references: 2 means "when sentence 2 starts", [2, 1.5] means 1.5 s later.
(function(){
  const {el,show,seg,clamp,svgLayer,wire,grow,scenes}=window.QR;
  const at=(m,a)=>Array.isArray(a)?(m[a[0]]||0)+(a[1]||0):(a===undefined?0:(m[a]||0));
  const blurIn=(n,p,s)=>{n.style.opacity=p;n.style.filter=p>=1?'':'blur('+((1-p)*14).toFixed(2)+'px)';n.style.transform='scale('+(1+(1-p)*(s||0.05))+')';};
  const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');
  const heading=d=>d.title?el('abs','<div class="cine-kicker">'+esc(d.kicker||'')+'</div><div class="cine-title" style="font-size:'+(d.title_size||58)+'px;margin-top:10px;max-width:1680px">'+esc(d.title)+'</div>',{left:'120px',top:'140px'}):null;
  const COL={ok:'#57E0CC',warn:'#F5C46B',bad:'#FF8A8A',dim:'rgba(255,255,255,.22)',violet:'#A99BFF'};

  // statement: big lines, one per mark. lines: [{text, at, color?, size?}]
  scenes.statement={build(d){
    const b={};const L=d.lines||[];const size=d.size||84,gap=size*1.42,top=540-((L.length-1)*gap)/2-size*0.62;
    b.h=heading(d);
    b.lines=L.map((x,i)=>el('abs cine-title',esc(x.text),{left:'120px',width:'1680px',textAlign:d.align||'center',top:(top+i*gap)+'px',fontSize:(x.size||size)+'px',color:COL[x.color]||x.color||'#F3F6FA'}));
    if(d.note)b.note=el('abs mono',esc(d.note.text),{left:'0',width:'1920px',textAlign:'center',top:'860px',fontSize:'24px',color:'#8E97A5'});
    return b;
  },draw(b,t,m,dur,d){
    if(b.h)blurIn(b.h,seg(t,at(m,d.title_at||0),0.8));
    b.lines.forEach((n,i)=>blurIn(n,seg(t,at(m,d.lines[i].at===undefined?i:d.lines[i].at),0.8)));
    if(b.note)blurIn(b.note,seg(t,at(m,d.note.at),0.6));
  }};

  // board: evidence cards, wires and state changes. cards: [{id,meta,text,x,y,w,at}], wires: [{from,to,at}],
  // events: [{at, card, state: ok|warn|bad|dim, tag}], result: {text, state, x, y, at}
  scenes.board={build(d){
    const b={cards:{},tags:{},wires:[]};b.h=heading(d);
    for(const c of d.cards||[]){
      const n=el('holo','<div class="meta">'+esc(c.meta||'')+'</div><div class="txt" style="font-size:'+(c.size||24)+'px">'+esc(c.text)+'</div>',{left:c.x+'px',top:c.y+'px',width:(c.w||400)+'px',padding:'18px 22px',...(c.accent?{borderColor:COL[c.accent]}:{})});
      b.cards[c.id]=n;b.tags[c.id]=el('tag ok','',{left:c.x+'px',top:'0px',opacity:0});}
    for(const c of d.cards||[]){const n=b.cards[c.id],g=b.tags[c.id];
      if(c.tag_side==='right'){g.style.left=(c.x+n.offsetWidth+14)+'px';g.style.top=(c.y+n.offsetHeight/2-16)+'px';}else g.style.top=(c.y+n.offsetHeight+10)+'px';}
    const s=svgLayer();
    for(const w of d.wires||[]){const A=b.cards[w.from],B=b.cards[w.to];
      const ax=A.offsetLeft,ay=A.offsetTop+A.offsetHeight/2,bx=B.offsetLeft,by=B.offsetTop+B.offsetHeight/2;
      const right=bx>ax;const x1=right?ax+A.offsetWidth:ax,x2=right?bx:bx+B.offsetWidth,mx=(x1+x2)/2;
      const p=wire(s,'M'+x1+' '+ay+' C'+mx+' '+ay+' '+mx+' '+by+' '+x2+' '+by);b.wires.push({p,w});}
    if(d.result)b.result=el('tag '+(d.result.state||'ok'),esc(d.result.text),{left:d.result.x+'px',top:d.result.y+'px',fontSize:'20px',padding:'9px 16px'});
    return b;
  },draw(b,t,m,dur,d){
    if(b.h)blurIn(b.h,seg(t,at(m,d.title_at||0),0.8));
    for(const c of d.cards||[])show(b.cards[c.id],seg(t,at(m,c.at),0.5),0);
    for(const {p,w} of b.wires){grow(p,seg(t,at(m,w.at),0.6));p.setAttribute('stroke','rgba(87,224,204,.6)');}
    for(const id in b.tags){b.tags[id].style.opacity=0;}
    for(const c of d.cards||[])b.cards[c.id].className='holo';
    for(const e of d.events||[]){if(t<at(m,e.at))continue;
      const n=b.cards[e.card],g=b.tags[e.card],p=seg(t,at(m,e.at),0.35);
      n.className='holo'+(e.state&&e.state!=='ok'?' '+e.state:'');
      if(e.tag){g.className='tag '+(e.state||'ok');g.textContent=e.tag;g.style.opacity=p;}
      for(const {p:wp,w} of b.wires)if(w.from===e.card||w.to===e.card&&e.wire)wp.setAttribute('stroke',COL[e.state]||COL.ok);
      if(e.glitch&&t<at(m,e.at)+0.6){n.style.transform='translate('+((Math.sin(t*90)*9)|0)+'px,0)';n.style.filter='drop-shadow(4px 0 0 rgba(255,80,120,.7)) drop-shadow(-4px 0 0 rgba(80,200,255,.7))';}else{n.style.filter='';}}
    if(b.result)show(b.result,seg(t,at(m,d.result.at),0.5),0);
  }};

  // terminal: real commands and their captured output. blocks: [{cmd, out, at, out_at}], notes: [{text, state, at}]
  const colourOut=s=>esc(s).replace(/\b(ADMIT|GENERATE)\b/g,'<span style="color:#57E0CC;font-weight:700">$1</span>')
    .replace(/\b(INCONCLUSIVE|WITHHELD|STALE_EVIDENCE|UNKNOWN_EVIDENCE|INSUFFICIENT_INDEPENDENT_EVIDENCE)\b/g,'<span style="color:#F5C46B">$1</span>')
    .replace(/\b(REFUSE|CONTRADICTION)\b/g,'<span style="color:#FF8A8A;font-weight:700">$1</span>').replace(/^(== .*)$/gm,'<span style="color:#EDEFF3">$1</span>');
  scenes.terminal={build(d){
    const b={};b.h=heading(d);
    b.term=el('holo','<div class="meta">'+esc(d.file||'terminal')+'</div><div class="code" style="font-size:'+(d.size||22)+'px;margin-top:12px;line-height:1.5;white-space:pre"></div>',{left:'120px',top:(d.title?'270px':'150px'),width:'1680px',padding:'22px 28px',minHeight:'420px'});
    b.pre=b.term.querySelector('.code');
    b.notes=(d.notes||[]).map((x,i)=>el('tag '+(x.state||'ok'),esc(x.text),{left:(120+(x.x||0))+'px',top:(x.y||840)+'px',fontSize:'19px',padding:'9px 16px'}));
    return b;
  },draw(b,t,m,dur,d){
    if(b.h)blurIn(b.h,seg(t,at(m,d.title_at||0),0.8));show(b.term,seg(t,at(m,d.term_at||0)+0.3,0.5),0);
    let html='',cursor=false;
    for(const k of d.blocks||[]){const st=at(m,k.at);if(t<st)break;
      let ot=st;
      if(k.cmd){const n=Math.floor(clamp((t-st)/(k.type||1.2))*k.cmd.length);
        html+='<span style="color:#57E0CC">$ </span>'+esc(k.cmd.slice(0,n));
        if(n<k.cmd.length){html+='<span class="cursor" style="height:24px"></span>';cursor=true;break;}
        html+='\n';ot=st+(k.type||1.2)+0.3;}
      if(k.out_at!==undefined)ot=at(m,k.out_at);
      const lines=(k.out||'').split('\n');const shown=Math.floor(clamp((t-ot)/(k.reveal||1.0))*lines.length);
      if(t>=ot)html+=colourOut(lines.slice(0,Math.max(0,shown)).join('\n'))+(shown?'\n':'');}
    if(!cursor&&d.blocks&&t>=at(m,d.blocks[0].at))html+='<span style="color:#57E0CC">$ </span>'+(Math.floor(t*2)%2?'<span class="cursor" style="height:24px"></span>':'');
    b.pre.innerHTML=html;
    b.notes.forEach((n,i)=>show(n,seg(t,at(m,d.notes[i].at),0.4),0));
  }};

  // incident: a verified real-world case. facts: [{k, v, at}], source: "..."
  scenes.incident={build(d){
    const b={};b.h=heading(d);
    b.card=el('holo bad','<div class="meta" style="color:#FF8A8A">'+esc(d.label||'REAL CASE')+'</div><div class="cine-title" style="font-size:44px;margin-top:8px">'+esc(d.case)+'</div>',{left:'120px',top:'270px',width:'1680px',padding:'26px 32px'});
    b.facts=(d.facts||[]).map((f,i)=>el('abs','<span class="mono" style="color:#8E97A5;font-size:20px;letter-spacing:.12em;display:inline-block;width:260px;text-transform:uppercase">'+esc(f.k)+'</span><span style="font-size:30px;color:#EDEFF3">'+esc(f.v)+'</span>',{left:'152px',top:(420+i*72)+'px',width:'1620px'}));
    b.src=el('abs mono','source · '+esc(d.source||''),{left:'152px',top:(440+(d.facts||[]).length*72)+'px',fontSize:'18px',color:'#8E97A5'});
    if(d.lesson)b.lesson=el('abs cine-title',esc(d.lesson.text),{left:'120px',width:'1680px',top:'850px',fontSize:'40px',color:'#57E0CC'});
    return b;
  },draw(b,t,m,dur,d){
    if(b.h)blurIn(b.h,seg(t,at(m,d.title_at||0),0.8));show(b.card,seg(t,at(m,d.card_at||0)+0.4,0.5),0);
    b.facts.forEach((n,i)=>show(n,seg(t,at(m,d.facts[i].at),0.4),12));show(b.src,seg(t,at(m,d.src_at===undefined?(d.facts.length?d.facts[d.facts.length-1].at:0):d.src_at)+0.6,0.4),0);
    if(b.lesson)blurIn(b.lesson,seg(t,at(m,d.lesson.at),0.7));
  }};

  // takeaway: what it does / what it does not. does: [{text, at}], doesnt: [{text, at}]
  scenes.takeaway={build(d){
    const b={};b.h=heading(d);
    const col=(label,items,x,cls)=>{const n=el('holo'+(cls?' '+cls:''),'<div class="meta" style="color:'+(cls?'#F5C46B':'#57E0CC')+'">'+label+'</div>'+items.map(i=>'<div class="ti" style="font-size:27px;line-height:1.35;color:#EDEFF3;margin-top:18px;opacity:0">'+esc(i.text)+'</div>').join(''),{left:x+'px',top:'280px',width:'800px',padding:'26px 30px',minHeight:'320px'});return n;};
    b.a=col(d.does_label||'QUALITYRAG DOES',d.does||[],120);b.n=col(d.doesnt_label||'IT DOES NOT',d.doesnt||[],1000,'warn');
    b.ai=[...b.a.querySelectorAll('.ti')];b.ni=[...b.n.querySelectorAll('.ti')];
    if(d.next)b.next=el('abs mono',esc(d.next.text),{left:'120px',top:'880px',fontSize:'24px',color:'#C4CAD4'});
    return b;
  },draw(b,t,m,dur,d){
    if(b.h)blurIn(b.h,seg(t,at(m,d.title_at||0),0.8));show(b.a,seg(t,at(m,d.cols_at||0)+0.3,0.5),0);show(b.n,seg(t,at(m,d.cols_at||0)+0.5,0.5),0);
    b.ai.forEach((n,i)=>show(n,seg(t,at(m,d.does[i].at),0.4),10));b.ni.forEach((n,i)=>show(n,seg(t,at(m,d.doesnt[i].at),0.4),10));
    if(b.next)show(b.next,seg(t,at(m,d.next.at),0.5),0);
  }};
})();
