function surface(canvas) {
  if (!canvas) return null;
  const {width:w,height:h}=canvas.getBoundingClientRect();
  if (!w || !h) return null;
  const scale=Math.min(devicePixelRatio||1,2);
  canvas.width=Math.round(w*scale); canvas.height=Math.round(h*scale);
  const ctx=canvas.getContext('2d');
  ctx.setTransform(scale,0,0,scale,0,0);
  return {ctx,w,h};
}

export function drawPlate(canvas, variant) {
  const s=surface(canvas); if(!s)return;
  const {ctx:c,w,h}=s;
  c.translate(w*.5,h*.52);
  const scale=Math.min(w/350,h/219);
  c.scale(scale,scale);
  const ink='#565d48', fill='#e7e7cf', shade='#d5d7bc';
  const proj=(x,y,z)=>[x*.89-y*.66,x*.34+y*.41-z*.87];
  function line(pts,color=ink,weight=.9,paint=null,closed=false) {
    c.beginPath(); pts.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));
    if(closed)c.closePath(); if(paint){c.fillStyle=paint;c.fill();}
    c.strokeStyle=color;c.lineWidth=weight;c.stroke();
  }
  const mesh=(arr,color,weight,paint,closed)=>line(arr.map(p=>proj(...p)),color,weight,paint,closed);
  function rim(x,r,dy=0,dz=0) {
    return Array.from({length:73},(_,i)=>{const a=i*Math.PI/36;return [x,dy+r*Math.cos(a),dz+r*Math.sin(a)];});
  }
  function cylinder(x1,x2,r,bore=0) {
    for(let x=x1;x<x2;x+=2.3)mesh(rim(x,r),ink,.54,shade,true);
    mesh(rim(x2,r),ink,1.1,fill,true);
    if(bore)mesh(rim(x2,bore),ink,1,shade,true);
  }
  function block(x1,x2,y1,y2,z1,z2) {
    mesh([[x1,y1,z2],[x2,y1,z2],[x2,y2,z2],[x1,y2,z2]],ink,.98,fill,true);
    mesh([[x1,y2,z2],[x2,y2,z2],[x2,y2,z1],[x1,y2,z1]],ink,.98,shade,true);
    mesh([[x2,y1,z2],[x2,y2,z2],[x2,y2,z1],[x2,y1,z1]],ink,1,fill,true);
  }
  function flange(a,b,r) {
    const n=r*.77;
    const face=[[-n,-r],[n,-r],[r,-n],[r,n],[n,r],[-n,r],[-r,n],[-r,-n]];
    for(let x=a;x<b;x+=2.2)mesh(face.map(([y,z])=>[x,y,z]),ink,.48,shade,true);
    mesh(face.map(([y,z])=>[b,y,z]),ink,1.1,fill,true);
    mesh(rim(b,r*.67),ink,.8,shade,true);
    for(const y of [-n,n])for(const z of [-n,n])mesh(rim(b,3.4,y*.92,z*.92),ink,.85,shade,true);
  }
  c.setLineDash([6,4,1,4]);
  mesh([[-155,0,0],[153,0,0]],'#919578',.7);
  c.setLineDash([]);
  if(variant===0) {
    flange(-118,-101,38);cylinder(-87,-77,29,16);
    for(let x=-62;x<0;x+=5)cylinder(x,x+2.7,34,15);
    flange(8,16,39); cylinder(31,47,25,12); cylinder(58,75,18,8);
    cylinder(87,117,11); cylinder(118,134,7);
  } else if(variant===1) {
    for(const z of [-36,-12,13,40]) {
      block(-70,67,-43,43,z-5,z);
      for(let y=-39;y<40;y+=5){
        const pts=Array.from({length:53},(_,i)=>{const x=-67+i*2.45;return [x,y,z+.8+2*Math.sin(x/13+y/9)];});
        mesh(pts,'#737a5b',.52);
      }
    }
  } else {
    block(-105,95,-38,38,-32,-18);
    for(const x of [-78,24]) {
      block(x,x+31,-30,30,-18,21);block(x-6,x+39,-37,37,21,32);
      for(let i=0;i<9;i++)mesh([[x-3+i*4.4,-34,32.4],[x-3+i*4.4,34,32.4]],ink,.5);
    }
    cylinder(61,109,8);cylinder(110,117,15);
  }
  for(const [x,y] of [[-151,-77],[151,77]]){line([[x-4,y],[x+4,y]],'#92967a',.75);line([[x,y-4],[x,y+4]],'#92967a',.75);}
}

export function drawRoutes(canvas) {
  const s=surface(canvas); if(!s)return;
  const {ctx:c,w,h}=s;
  c.scale(w/100,h/100);
  function route(points,color,thick) {
    c.beginPath();c.moveTo(...points[0]);
    for(const a of points.slice(1)) {
      if(a.length===4)c.quadraticCurveTo(...a); else c.lineTo(...a);
    }
    c.lineCap='round';c.lineJoin='round';c.lineWidth=thick;c.strokeStyle=color;c.stroke();
  }
  const green='#dafa8b', ice='#6adce4';
  route([[-2,24],[38,24],[40,24,42,30],[50,54],[51,57,54,57],[62,57],[64,57,66,52],[70,43],[71,40,74,40],[103,40]],green,1.24);
  route([[-2,75],[13,75],[16,75,18,70],[21,63],[23,58,26,58],[32,58],[35,58,37,63],[39,67],[40,68,42,68],[59,68],[62,68,64,62],[70,46],[72,40,74,40],[83,40],[86,40,88,47],[92,59],[94,65,97,65],[103,65]],ice,1.15);
  for(const [x,y] of [[11,24],[35,24],[29,58],[57,57],[90,40]]) {
    c.beginPath();c.ellipse(x,y,.48,Math.max(.62,w/h*.48),0,0,Math.PI*2);c.fillStyle='#162c35';c.fill();c.lineWidth=.35;c.strokeStyle='#b7d7c2';c.stroke();
  }
}
