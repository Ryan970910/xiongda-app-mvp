const options = {
  original: '原版', rules: '公文眉线', transfer: '双线交接',
  folders: '卷宗页签', calendar: '值班日签', folds: '办理折页',
};
const steps = [
  ['科研立项', '确认项目清单', '#projects'],
  ['费用归集', '关联项目与凭证', '#tasks/finance'],
  ['交付归档', '留存审核与确认', '#archive'],
];
const numbered = i => `0${i+1}`;
const flowNav = links => `<nav class="hp-steps" aria-label="研发服务流程">${links.join('')}</nav>`;
function stepLinks(variant) {
  return flowNav(steps.map(([title, sub, href],i) => {
    const number = `<span class="hp-no" aria-hidden="true">${numbered(i)}</span>`;
    const content = `<span class="hp-copy"><strong>${title}</strong><small>${sub}</small></span>`;
    const end = '<span class="hp-end" aria-hidden="true">↗</span>';
    if (variant==='calendar') return `<a href="${href}">${number}<strong>${title}</strong><small>${sub}</small>${end}</a>`;
    return `<a href="${href}">${number}${content}${end}</a>`;
  }));
}
const title = '<h1>研发服务工作台</h1>';
const meta = ({today,roleName}) => `<p class="hp-meta"><span>${today}</span><i></i><span>${roleName}视角</span></p>`;

function design(key, ctx, foldIndex) {
  const {orderButton}=ctx;
  if (key==='rules') return `<div class="hp-letter"><div class="hp-line-head">${title}${orderButton}</div>${meta(ctx)}</div>${stepLinks(key)}`;
  if (key==='transfer') return `<div class="hp-desk">${title}${meta(ctx)}${orderButton}</div><div class="hp-route"><div class="hp-route-head"><strong>办理路线</strong><span><i></i> 科研 <i></i> 财务</span></div>${stepLinks(key)}</div>`;
  if (key==='folders') return `<div class="hp-filing"><div class="hp-file-head">${title}${orderButton}</div>${meta(ctx)}</div>${stepLinks(key)}`;
  if (key==='calendar') {
    const now = new Date();
    const month = `${now.getFullYear()} / ${String(now.getMonth()+1).padStart(2,'0')}`;
    const weekday = now.toLocaleDateString('zh-CN',{weekday:'long'});
    return `<div class="hp-calendar-intro"><time class="hp-date" datetime="${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}"><small>${month}</small><b>${String(now.getDate()).padStart(2,'0')}</b><span>${weekday}</span></time><div class="hp-duty">${title}<p class="hp-meta">${ctx.roleName}视角</p>${orderButton}</div></div>${stepLinks(key)}`;
  }
  return `<div class="hp-fold-head"><div>${title}${meta(ctx)}</div>${orderButton}</div>
    <div class="hp-fold-strip" aria-label="研发服务流程">${steps.map(([label,sub,href],i)=>`<div class="hp-fold" data-active="${i===foldIndex}">
      <button type="button" data-fold="${i}" aria-expanded="${i===foldIndex}" aria-controls="hp-fold-${i}"><span class="hp-no">${numbered(i)}</span><strong>${label}</strong><span class="hp-plus" aria-hidden="true">${i===foldIndex?'−':'+'}</span></button>
      <div class="hp-fold-detail" id="hp-fold-${i}" ${i===foldIndex?'':'hidden'}><span>${sub}</span><a href="${href}">进入${label} →</a></div></div>`).join('')}</div>`;
}

export function configureDashboardHeader(render) {
  let key = new URLSearchParams(location.search).get('header');
  let foldIndex=0;
  const renderHeader = ctx => key==='original' ? null : `<section class="hp hp-${key}" aria-label="工作台与办理入口">${design(key,ctx,foldIndex)}</section>`;
  if (!Object.hasOwn(options,key)) {
    key='folders';
    return renderHeader;
  }
  const menu=document.createElement('nav');
  menu.className='hp-review'; menu.setAttribute('aria-label','顶部方案对照');
  menu.innerHTML=`<strong>顶部对照</strong><div>${Object.entries(options).map(([id,label])=>`<a href="?header=${id}#dashboard" data-sample="${id}">${label}</a>`).join('')}</div><a class="hp-sheet-link" href="./header-options/compare.webp" target="_blank" rel="noopener">看对照图 ↗</a>`;
  document.querySelector('.shell').before(menu);
  function markActive() {
    for(const a of menu.querySelectorAll('[data-sample]')){
      if(a.dataset.sample===key) a.setAttribute('aria-current','true');
      else a.removeAttribute('aria-current');
    }
  }
  markActive();
  window.addEventListener('popstate',()=>{
    const previous=new URLSearchParams(location.search).get('header');
    if(previous!==key && Object.hasOwn(options,previous)) {
      key=previous; markActive(); render();
    }
  });
  menu.addEventListener('click',e=>{
    const a=e.target.closest('[data-sample]');
    if(!a || e.defaultPrevented || e.button!==0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    key=a.dataset.sample;
    history.replaceState(null,'',a.href); markActive(); render(); window.scrollTo(0,0);
  });
  document.querySelector('main').addEventListener('click',e=>{
    const b=e.target.closest('.hp-fold button[data-fold]');
    if(!b) return;
    const i=Number(b.dataset.fold);
    foldIndex=foldIndex===i ? -1 : i;
    render();
    document.querySelector('[data-fold="'+i+'"]')?.focus({preventScroll:true});
  });
  return renderHeader;
}
