/* ============================================================
   Smile.AI — клиентская логика киоска
   • аудио-волна в круге (canvas), реагирует на «амплитуду» речи
   • процедурный фон (медузы/частицы) когда нет видеофайла
   • синхронизация состояния через SSE (/api/events)
   • режимы: idle · greeting · listening · thinking · speaking
   ============================================================ */

(() => {
  "use strict";

  const body = document.body;
  const statusLabel = document.getElementById("status-label");
  const subtitleEl = document.getElementById("subtitle");
  const hudText = document.getElementById("hud-text");
  const jelly = document.getElementById("jellyfish");

  const STATUS_RU = {
    idle: "",
    greeting: "Здравствуйте",
    listening: "Слушаю…",
    thinking: "Думаю…",
    speaking: "Говорю…",
  };

  // ── Глобальное состояние ────────────────────────────────
  const state = {
    mode: "idle",
    amplitude: 0,      // 0..1 целевая
    ampSmooth: 0,      // сглаженная
    speaking: false,
  };

  function setMode(mode) {
    if (!STATUS_RU.hasOwnProperty(mode)) return;
    state.mode = mode;
    body.dataset.mode = mode;
    statusLabel.textContent = STATUS_RU[mode];
    hudText.textContent = mode.toUpperCase();
    state.speaking = mode === "speaking";
  }

  function setSubtitle(text, who) {
    if (!text) {
      subtitleEl.classList.remove("show");
      return;
    }
    subtitleEl.textContent = text;
    subtitleEl.classList.remove("user", "bot");
    subtitleEl.classList.add(who === "user" ? "user" : "bot", "show");
  }

  // ============================================================
  //  Аудио-волна в круге
  // ============================================================
  const wave = document.getElementById("wave");
  const wctx = wave.getContext("2d");

  function sizeWave() {
    const dpr = window.devicePixelRatio || 1;
    const r = wave.getBoundingClientRect();
    wave.width = Math.max(2, r.width * dpr);
    wave.height = Math.max(2, r.height * dpr);
    wctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // Концентрические волны, расходящиеся из центра круга (как у голосового
  // ассистента). Когда Оливия говорит — волны ярче и быстрее по амплитуде
  // речи; в остальных режимах спокойнее. Заменяет прежнюю «дугу».
  function drawWave(t) {
    const r = wave.getBoundingClientRect();
    const W = r.width, H = r.height;
    wctx.clearRect(0, 0, W, H);

    const cx = W / 2, cy = H / 2;
    const maxR = Math.min(W, H) * 0.5;   // до края круга

    // энергия и скорость волн зависят от режима
    let energy, speed;
    if (state.mode === "speaking") {
      energy = 0.5 + state.ampSmooth * 0.9;   // ярче на громких местах речи
      speed = 1.0 + state.ampSmooth * 0.8;
    } else if (state.mode === "listening") {
      energy = 0.32; speed = 0.55;
    } else if (state.mode === "thinking") {
      energy = 0.20; speed = 0.35;
    } else {
      energy = 0.22; speed = 0.45;            // idle/greeting — лёгкое дыхание
    }

    const RINGS = 5;
    const cycle = 4200 / speed;               // «жизнь» одной волны, мс

    wctx.save();
    wctx.globalCompositeOperation = "lighter"; // волны светятся, складываясь

    for (let i = 0; i < RINGS; i++) {
      // фаза 0..1: волна рождается в центре и уходит к краю
      const phase = ((t / cycle) + i / RINGS) % 1;
      const wobble = state.mode === "speaking"
        ? 1 + 0.06 * Math.sin(t / 90 + i) * state.ampSmooth : 1;
      const rad = phase * maxR * wobble;
      if (rad < 2) continue;
      // яркость: ноль в центре и у края, максимум посередине пути
      const fade = Math.sin(Math.PI * phase);
      const alpha = Math.min(0.9, fade * energy);
      if (alpha <= 0.01) continue;

      wctx.beginPath();
      wctx.arc(cx, cy, rad, 0, Math.PI * 2);
      wctx.strokeStyle = `rgba(226, 212, 255, ${alpha})`;  // бело-фиолетовый
      wctx.lineWidth = 2.4 * (0.6 + fade);
      wctx.shadowColor = "rgba(180, 140, 255, 0.65)";
      wctx.shadowBlur = 16;
      wctx.stroke();
    }
    wctx.shadowBlur = 0;

    // мягкое светящееся ядро в центре (пульсирует с речью)
    const coreA = state.mode === "speaking"
      ? 0.16 + 0.28 * state.ampSmooth : 0.10;
    const core = wctx.createRadialGradient(cx, cy, 0, cx, cy, maxR * 0.55);
    core.addColorStop(0, `rgba(242, 232, 255, ${coreA})`);
    core.addColorStop(0.5, `rgba(200, 160, 255, ${coreA * 0.4})`);
    core.addColorStop(1, "rgba(150, 110, 255, 0)");
    wctx.fillStyle = core;
    wctx.beginPath();
    wctx.arc(cx, cy, maxR * 0.55, 0, Math.PI * 2);
    wctx.fill();

    wctx.restore();
  }

  // ============================================================
  //  Процедурный фон (медузы/частицы) — fallback без видео
  // ============================================================
  const bg = document.getElementById("bg-canvas");
  const bctx = bg.getContext("2d");
  let particles = [];

  function sizeBg() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    bg.width = window.innerWidth * dpr;
    bg.height = window.innerHeight * dpr;
    bctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    initParticles();
  }

  function initParticles() {
    const w = window.innerWidth, h = window.innerHeight;
    const count = Math.round((w * h) / 9000);
    particles = [];
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        r: Math.random() * 1.8 + 0.3,
        s: Math.random() * 0.25 + 0.05,
        tw: Math.random() * Math.PI * 2,
      });
    }
  }

  // ═══════════════════════════════════════════════════════
  //  Медузы — биолюминесцентные, с физикой щупалец
  // ═══════════════════════════════════════════════════════
  function hexRGB(h){const n=parseInt(h.slice(1),16);return[(n>>16)&255,(n>>8)&255,n&255]}
  function rgba(r,g,b,a){return`rgba(${r|0},${g|0},${b|0},${a})`}
  function lit(r,g,b,k){return[Math.min(255,r+k),Math.min(255,g+k),Math.min(255,b+k)]}
  function mix(a,b,t){return a+(b-a)*t}

  const PALETTE=[
    {base:"#8855ff",glow:"#c4a0ff",core:"#e8d0ff"},
    {base:"#22ccee",glow:"#80eeff",core:"#d0faff"},
    {base:"#ff5599",glow:"#ff99c4",core:"#ffd4e8"},
    {base:"#ff9933",glow:"#ffcc80",core:"#fff0d0"},
    {base:"#44ddaa",glow:"#88ffcc",core:"#d0ffe8"},
    {base:"#bb66ff",glow:"#dd99ff",core:"#f0d8ff"},
  ];
  const jellies=[];
  let _prevT=0;

  function mkChain(n,x,y,sp){
    const s=[];
    for(let i=0;i<n;i++) s.push({x:x+sp*0.1*i,y:y+i*sp,ox:x,oy:y+i*sp});
    return s;
  }

  function makeJelly(x,y,depth){
    const sz=35+depth*80+Math.random()*40;
    const pal=PALETTE[Math.floor(Math.random()*PALETTE.length)];
    const [cr,cg,cb]=hexRGB(pal.base);
    const [gr,gg,gb]=hexRGB(pal.glow);
    const [lr,lg,lb]=hexRGB(pal.core);
    // oral arms — толстые, короткие, волнистые (4 шт)
    const arms=[];
    for(let i=0;i<4;i++){
      arms.push({
        segs:mkChain(7+Math.floor(Math.random()*4),x,y,sz*0.2),
        off:(i-1.5)/1.5*0.6,
        w:2+Math.random()*2.5,
        wave:0.8+Math.random()*0.6,
      });
    }
    // thin trailing tentacles — длинные, тонкие (8-12 шт)
    const trails=[];
    const nTrail=8+Math.floor(Math.random()*5);
    for(let i=0;i<nTrail;i++){
      trails.push({
        segs:mkChain(14+Math.floor(Math.random()*10),x,y,sz*0.18),
        off:(i-(nTrail-1)/2)/((nTrail-1)/2)*0.85,
        w:0.4+Math.random()*0.9,
        wave:0.5+Math.random()*0.8,
      });
    }
    // bell edge vertices for undulation
    const nEdge=24;
    const edgePhases=[];
    for(let i=0;i<nEdge;i++) edgePhases.push(Math.random()*Math.PI*2);
    // radial channels (внутренние каналы)
    const nChan=6+Math.floor(Math.random()*4);

    return{
      x,y,vx:0,vy:0,size:sz,depth,
      cr,cg,cb,gr,gg,gb,lr,lg,lb,
      phase:Math.random()*Math.PI*2,
      pulsePhase:Math.random()*Math.PI*2,
      pulseSpeed:0.0014+Math.random()*0.0008,
      pulse:0,angle:0,
      arms,trails,edgePhases,nEdge,nChan,
      // bio-luminescence
      bioPhase:Math.random()*Math.PI*2,
      bioSpeed:0.001+Math.random()*0.001,
      // trail particles
      sparks:[],
    };
  }

  function initJellies(){
    const w=window.innerWidth,h=window.innerHeight;
    jellies.length=0;
    for(let i=0;i<7;i++){
      const d=0.2+Math.random()*0.8;
      jellies.push(makeJelly(Math.random()*w,Math.random()*h,d));
    }
    jellies.sort((a,b)=>a.depth-b.depth);
  }

  function simChain(segs,ax,ay,t,wave,grav,damp,segLen,spd){
    segs[0].x=ax; segs[0].y=ay;
    for(let i=1;i<segs.length;i++){
      const s=segs[i];
      const dx=s.x-s.ox, dy=s.y-s.oy;
      s.ox=s.x; s.oy=s.y;
      s.x+=dx*damp+Math.sin(t*0.0025+i*0.7)*wave*spd;
      s.y+=dy*damp+grav*spd;
    }
    for(let iter=0;iter<4;iter++){
      for(let i=1;i<segs.length;i++){
        const a=segs[i-1],b=segs[i];
        const ddx=b.x-a.x,ddy=b.y-a.y;
        const d=Math.sqrt(ddx*ddx+ddy*ddy)||0.001;
        const f=(d-segLen)/d*0.5;
        if(i===1){b.x-=ddx*f*2;b.y-=ddy*f*2;}
        else{a.x+=ddx*f;a.y+=ddy*f;b.x-=ddx*f;b.y-=ddy*f;}
      }
    }
  }

  function updateJelly(j,t,dt,w,h){
    const spd=dt/16;
    // pulsation — asymmetric: fast contract, slow expand (like real jellyfish)
    const raw=Math.sin(t*j.pulseSpeed+j.pulsePhase);
    const shaped=raw>0?Math.pow(raw,0.6):-Math.pow(-raw,1.8)*0.4;
    j.pulse=shaped*0.22;
    // thrust on contraction
    const thrust=raw>0.2?(raw-0.2)*0.08*j.depth:0;
    j.vy+=(-0.012-thrust)*j.depth*spd;
    j.vx+=Math.sin(t*0.0002+j.phase)*0.006*spd;
    // gentle horizontal drift
    j.vx+=(Math.sin(t*0.00013+j.phase*2)-0.5)*0.002*spd;
    j.vx*=0.994; j.vy*=0.997;
    j.x+=j.vx*spd; j.y+=j.vy*spd;
    j.angle+=(j.vx*0.02-j.angle*0.04)*spd;
    if(j.y<-j.size*6){j.y=h+j.size*4;j.x=Math.random()*w;}
    if(j.x<-j.size*4) j.x=w+j.size*3;
    if(j.x>w+j.size*4) j.x=-j.size*3;

    const bw=j.size*(1-j.pulse*0.4);
    const grav=0.05,damp=0.965;
    // update arms
    for(const a of j.arms){
      const ax=j.x+a.off*bw*0.7, ay=j.y+j.size*0.05;
      simChain(a.segs,ax,ay,t+a.off*50,a.wave,grav,damp,j.size*0.18,spd);
    }
    // update trails
    for(const tr of j.trails){
      const ax=j.x+tr.off*bw*0.9, ay=j.y+j.size*0.02;
      simChain(tr.segs,ax,ay,t+tr.off*80,tr.wave*0.6,grav*0.7,0.975,j.size*0.15,spd);
    }
    // sparks
    if(Math.random()<0.08*j.depth){
      j.sparks.push({
        x:j.x+(Math.random()-0.5)*bw,
        y:j.y+Math.random()*j.size*0.5,
        vx:(Math.random()-0.5)*0.3,
        vy:Math.random()*0.4+0.1,
        life:1,
      });
    }
    for(let i=j.sparks.length-1;i>=0;i--){
      const s=j.sparks[i];
      s.x+=s.vx*spd; s.y+=s.vy*spd;
      s.life-=0.012*spd;
      if(s.life<=0) j.sparks.splice(i,1);
    }
  }

  function drawChain(ctx,segs,w,r,g,b,alpha,glow){
    if(segs.length<2) return;
    ctx.beginPath();
    ctx.moveTo(segs[0].x,segs[0].y);
    for(let i=1;i<segs.length-1;i++){
      const mx=(segs[i].x+segs[i+1].x)/2,my=(segs[i].y+segs[i+1].y)/2;
      ctx.quadraticCurveTo(segs[i].x,segs[i].y,mx,my);
    }
    const last=segs[segs.length-1];
    ctx.lineTo(last.x,last.y);
    if(glow){ctx.shadowColor=rgba(r,g,b,alpha*0.3);ctx.shadowBlur=6;}
    const grad=ctx.createLinearGradient(segs[0].x,segs[0].y,last.x,last.y);
    grad.addColorStop(0,rgba(r,g,b,alpha*0.7));
    grad.addColorStop(0.5,rgba(r,g,b,alpha*0.35));
    grad.addColorStop(1,rgba(r,g,b,0));
    ctx.strokeStyle=grad;
    ctx.lineWidth=w;
    ctx.lineCap="round";
    ctx.lineJoin="round";
    ctx.stroke();
    ctx.shadowBlur=0;
  }

  function drawJelly(ctx,j,t){
    const a=0.2+j.depth*0.6;
    const {cr,cg,cb,gr,gg,gb,lr,lg,lb}=j;
    const bw=j.size*(1-j.pulse*0.4);
    const bh=j.size*(0.78+j.pulse*0.15);
    const cx=j.x,cy=j.y;
    // bio-luminescence pulse
    const bio=0.6+0.4*Math.sin(t*j.bioSpeed+j.bioPhase);

    ctx.save();

    // 1) thin trailing tentacles (behind everything)
    for(const tr of j.trails){
      drawChain(ctx,tr.segs,tr.w*(1+j.pulse*0.3),cr,cg,cb,a*0.4*bio,false);
    }

    // 2) outer glow halo
    const haloR=bw*1.6;
    const hg=ctx.createRadialGradient(cx,cy-bh*0.3,bw*0.2,cx,cy-bh*0.2,haloR);
    hg.addColorStop(0,rgba(gr,gg,gb,a*0.12*bio));
    hg.addColorStop(0.5,rgba(cr,cg,cb,a*0.06*bio));
    hg.addColorStop(1,rgba(cr,cg,cb,0));
    ctx.fillStyle=hg;
    ctx.fillRect(cx-haloR,cy-bh-haloR*0.5,haloR*2,bh+haloR*1.5);

    // 3) oral arms (thick, in front of glow, behind bell)
    for(const arm of j.arms){
      drawChain(ctx,arm.segs,arm.w*(1+j.pulse*0.5),gr,gg,gb,a*0.55*bio,true);
    }

    // 4) bell — undulating edge path
    ctx.beginPath();
    // top dome via bezier
    ctx.moveTo(cx-bw,cy);
    ctx.bezierCurveTo(cx-bw,cy-bh*0.55,cx-bw*0.5,cy-bh,cx,cy-bh);
    ctx.bezierCurveTo(cx+bw*0.5,cy-bh,cx+bw,cy-bh*0.55,cx+bw,cy);
    // undulating bottom edge
    const nE=j.nEdge;
    for(let i=nE;i>=0;i--){
      const frac=i/nE;
      const ex=cx+bw-frac*bw*2;
      const wave=Math.sin(frac*Math.PI*5+t*0.004+j.edgePhases[i%nE])*bh*0.06;
      const scallop=Math.sin(frac*Math.PI*nE*0.5)*bh*0.025;
      const ey=cy+wave+scallop+bh*0.04;
      ctx.lineTo(ex,ey);
    }
    ctx.closePath();

    // multi-layer gradient fill
    // layer 1: base body — dense center
    const rg1=ctx.createRadialGradient(cx,cy-bh*0.4,0,cx,cy-bh*0.25,bw*1.2);
    rg1.addColorStop(0,rgba(lr,lg,lb,a*0.75*bio));
    rg1.addColorStop(0.2,rgba(gr,gg,gb,a*0.5*bio));
    rg1.addColorStop(0.5,rgba(cr,cg,cb,a*0.3));
    rg1.addColorStop(0.8,rgba(...lit(cr,cg,cb,40),a*0.55*bio));
    rg1.addColorStop(1,rgba(cr,cg,cb,0.01));
    ctx.fillStyle=rg1;
    ctx.fill();

    // layer 2: edge glow (additive)
    ctx.save();
    ctx.globalCompositeOperation="lighter";
    const rg2=ctx.createRadialGradient(cx,cy-bh*0.35,bw*0.5,cx,cy-bh*0.3,bw*1.05);
    rg2.addColorStop(0,rgba(cr,cg,cb,0));
    rg2.addColorStop(0.6,rgba(cr,cg,cb,0));
    rg2.addColorStop(0.82,rgba(gr,gg,gb,a*0.35*bio));
    rg2.addColorStop(0.95,rgba(...lit(gr,gg,gb,50),a*0.45*bio));
    rg2.addColorStop(1,rgba(cr,cg,cb,0));
    ctx.fillStyle=rg2;
    ctx.fill();
    ctx.restore();

    // 5) inner membrane ring
    ctx.beginPath();
    const mw=bw*0.88,mh=bh*0.88;
    ctx.moveTo(cx-mw,cy);
    ctx.bezierCurveTo(cx-mw,cy-mh*0.5,cx-mw*0.48,cy-mh,cx,cy-mh);
    ctx.bezierCurveTo(cx+mw*0.48,cy-mh,cx+mw,cy-mh*0.5,cx+mw,cy);
    ctx.strokeStyle=rgba(...lit(gr,gg,gb,40),a*0.3*bio);
    ctx.lineWidth=1.2;
    ctx.stroke();

    // second inner ring (smaller)
    ctx.beginPath();
    const m2w=bw*0.65,m2h=bh*0.65;
    ctx.moveTo(cx-m2w,cy+bh*0.03);
    ctx.bezierCurveTo(cx-m2w,cy-m2h*0.45,cx-m2w*0.45,cy-m2h,cx,cy-m2h);
    ctx.bezierCurveTo(cx+m2w*0.45,cy-m2h,cx+m2w,cy-m2h*0.45,cx+m2w,cy+bh*0.03);
    ctx.strokeStyle=rgba(lr,lg,lb,a*0.15*bio);
    ctx.lineWidth=0.8;
    ctx.stroke();

    // 6) radial channels (veins visible through bell)
    ctx.globalAlpha=a*0.2*bio;
    for(let i=0;i<j.nChan;i++){
      const ang=-Math.PI*0.15+Math.PI*0.3*(i/(j.nChan-1))-Math.PI/2;
      const wave2=Math.sin(t*0.002+i*1.3+j.phase)*0.08;
      ctx.beginPath();
      ctx.moveTo(cx,cy-bh*0.15);
      const endX=cx+Math.cos(ang+wave2)*bw*0.85;
      const endY=cy-bh*0.15+Math.sin(ang+wave2)*bh*0.75;
      const cpX=cx+Math.cos(ang+wave2)*bw*0.4;
      const cpY=cy-bh*0.15+Math.sin(ang+wave2)*bh*0.35;
      ctx.quadraticCurveTo(cpX,cpY,endX,endY);
      ctx.strokeStyle=rgba(lr,lg,lb,1);
      ctx.lineWidth=0.7;
      ctx.stroke();
    }
    ctx.globalAlpha=1;

    // 7) specular highlights
    // main highlight
    const hx=cx-bw*0.22,hy=cy-bh*0.72;
    const sg=ctx.createRadialGradient(hx,hy,0,hx,hy,bw*0.32);
    sg.addColorStop(0,rgba(255,255,255,a*0.4*bio));
    sg.addColorStop(0.5,rgba(255,255,255,a*0.1));
    sg.addColorStop(1,"rgba(255,255,255,0)");
    ctx.fillStyle=sg;
    ctx.beginPath();
    ctx.ellipse(hx,hy,bw*0.25,bh*0.15,-0.4,0,Math.PI*2);
    ctx.fill();
    // secondary highlight
    const h2x=cx+bw*0.18,h2y=cy-bh*0.82;
    const sg2=ctx.createRadialGradient(h2x,h2y,0,h2x,h2y,bw*0.14);
    sg2.addColorStop(0,rgba(255,255,255,a*0.25*bio));
    sg2.addColorStop(1,"rgba(255,255,255,0)");
    ctx.fillStyle=sg2;
    ctx.beginPath();
    ctx.ellipse(h2x,h2y,bw*0.1,bh*0.06,-0.2,0,Math.PI*2);
    ctx.fill();

    // 8) bioluminescent core glow (pulsing)
    ctx.save();
    ctx.globalCompositeOperation="lighter";
    const coreGlow=ctx.createRadialGradient(cx,cy-bh*0.35,0,cx,cy-bh*0.35,bw*0.5);
    coreGlow.addColorStop(0,rgba(lr,lg,lb,a*0.3*bio*bio));
    coreGlow.addColorStop(0.4,rgba(gr,gg,gb,a*0.12*bio));
    coreGlow.addColorStop(1,rgba(cr,cg,cb,0));
    ctx.fillStyle=coreGlow;
    ctx.beginPath();
    ctx.ellipse(cx,cy-bh*0.35,bw*0.45,bh*0.35,0,0,Math.PI*2);
    ctx.fill();
    ctx.restore();

    // 9) sparks / bioluminescent particles
    for(const sp of j.sparks){
      const sa=sp.life*a*0.6*bio;
      ctx.beginPath();
      ctx.arc(sp.x,sp.y,1+sp.life,0,Math.PI*2);
      ctx.fillStyle=rgba(lr,lg,lb,sa);
      ctx.fill();
    }

    ctx.restore();
  }

  function drawBg(t){
    if(jelly.style.display==="block") return;
    const w=window.innerWidth,h=window.innerHeight;
    const dt=_prevT?Math.min(t-_prevT,50):16;
    _prevT=t;

    // deep ocean gradient
    const g=bctx.createLinearGradient(0,0,0,h);
    g.addColorStop(0,"#030612");
    g.addColorStop(0.3,"#060d1f");
    g.addColorStop(0.7,"#0a0f24");
    g.addColorStop(1,"#030508");
    bctx.fillStyle=g;
    bctx.fillRect(0,0,w,h);

    // underwater light rays from above
    bctx.save();
    bctx.globalCompositeOperation="lighter";
    for(let i=0;i<3;i++){
      const rx=w*0.2+i*w*0.3+Math.sin(t*0.0002+i*2)*w*0.05;
      const rg=bctx.createLinearGradient(rx,0,rx+w*0.08,h*0.7);
      rg.addColorStop(0,`rgba(60,100,180,${0.015+0.01*Math.sin(t*0.0005+i)})`);
      rg.addColorStop(1,"rgba(60,100,180,0)");
      bctx.fillStyle=rg;
      bctx.beginPath();
      bctx.moveTo(rx-w*0.03,0);
      bctx.lineTo(rx+w*0.05,0);
      bctx.lineTo(rx+w*0.12,h*0.7);
      bctx.lineTo(rx-w*0.01,h*0.7);
      bctx.fill();
    }
    bctx.restore();

    // particle stars
    for(const p of particles){
      p.y-=p.s;
      p.tw+=0.025;
      if(p.y<-5){p.y=h+5;p.x=Math.random()*w;}
      const pa=0.25+0.25*Math.sin(p.tw);
      bctx.beginPath();
      bctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      bctx.fillStyle=rgba(160,200,255,pa);
      bctx.fill();
    }

    for(const j of jellies){
      updateJelly(j,t,dt,w,h);
      drawJelly(bctx,j,t);
    }
  }

  // ============================================================
  //  Главный цикл анимации
  // ============================================================
  function loop(t) {
    // сглаживание амплитуды
    state.ampSmooth += (state.amplitude - state.ampSmooth) * 0.18;
    if (state.mode === "speaking") {
      // если внешняя амплитуда не приходит — генерим «речевую» огибающую
      if (state._extAmpAt === undefined || t - state._extAmpAt > 400) {
        state.amplitude = 0.35 + 0.45 * Math.abs(Math.sin(t / 140)) * Math.random();
      }
    } else {
      state.amplitude = 0;
    }

    drawBg(t);
    drawWave(t);
    requestAnimationFrame(loop);
  }

  // ============================================================
  //  Подключение к серверу (SSE)
  // ============================================================
  function connect() {
    let es;
    try {
      es = new EventSource("/api/events");
    } catch (e) {
      console.warn("SSE недоступен, остаюсь в демо-режиме фона", e);
      return;
    }
    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        handleEvent(msg);
      } catch (_) {}
    };
    es.onerror = () => { hudText.textContent = state.mode.toUpperCase() + " (offline)"; };
  }

  function handleEvent(msg) {
    if (msg.type === "mode") setMode(msg.mode);
    else if (msg.type === "subtitle") setSubtitle(msg.text, msg.who);
    else if (msg.type === "amplitude") {
      state.amplitude = Math.max(0, Math.min(1.2, msg.value));
      state._extAmpAt = performance.now();
    } else if (msg.type === "clear_subtitle") setSubtitle("");
  }

  // ── Видео медуз, если файл доступен ─────────────────────
  function tryVideo() {
    const src = "/assets/jellyfish.mp4";
    fetch(src, { method: "HEAD" })
      .then((r) => {
        if (r.ok) {
          jelly.src = src;
          jelly.style.display = "block";
          jelly.play().catch(() => {});
        }
      })
      .catch(() => {});
  }

  // ── init ────────────────────────────────────────────────
  function resizeAll() { sizeBg(); sizeWave(); initJellies(); }
  window.addEventListener("resize", resizeAll);

  // ручной триггер для отладки без сервера: клавиши 1..5
  window.addEventListener("keydown", (e) => {
    const map = { "1": "idle", "2": "greeting", "3": "listening", "4": "thinking", "5": "speaking" };
    if (map[e.key]) setMode(map[e.key]);
  });

  sizeBg();
  sizeWave();
  initJellies();
  setMode("idle");
  tryVideo();
  connect();
  requestAnimationFrame(loop);

  // экспорт для скриншот-скриптов / отладки
  window.SmileUI = { setMode, setSubtitle, state };
})();
