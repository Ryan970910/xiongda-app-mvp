import { actionsFor, actionLabels, editable, localDate, projectsFor, roles, statuses } from './model.js';

export const designs = {
  hall: ['综合办事大厅','一站检索','按事项、订单号或客户名称检索办理记录。'],
  intake: ['一窗受理台','受理派单','选择服务订单和作业类型，核对后直接派单。'],
  review: ['联合会审室','审核复核','并排核对提交版本、变更字段和审核意见。'],
  archive: ['公文案卷馆','档案查阅','按客户调卷，翻看材料目录、批次和流转记录。'],
  calendar: ['督办日历','时限督办','点选日期查看到期任务，跨月检查办理期限。'],
  funds: ['资金核验台','财务核对','从项目预算下钻到实际录入的费用及凭证。'],
  liaison: ['双线协办室','科研财务协同','按订单跟踪两条业务线，定位补件问题。'],
  guide: ['事项导办册','事项指引','选择办理事项，逐步核对材料、流程和交付物。'],
  monitor: ['运行指挥屏','运行监测','切换时限区间，筛出需要督办的具体事项。'],
  access: ['大字办事窗口','简明办理','按办理意图分步导航，可放大文字进行操作。'],
};
export const legacy = { transit:'hall',proof:'review',optics:'intake',departures:'monitor',ledger:'funds',strata:'archive',swiss:'access',film:'review',weave:'liaison',stage:'guide' };
const verdicts = { assigned:'承办人接件',working:'编制作业底稿',revision:'按意见修改',lead:'主管初审',reviewer:'经理复审',director:'总监终审',customer:'登记客户确认',complete:'待归档',archived:'查阅档案' };
const e = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const href = (page,id) => '#' + page + (id ? '/' + encodeURIComponent(id) : '');
const link = (label,page,id) => `<a class="c-link" href="${href(page,id)}">${e(label)} <span aria-hidden="true">↗</span></a>`;
const tab = (key,value,label,active) => `<button type="button" class="pick" data-set="${key}" data-value="${e(value)}" aria-pressed="${String(value)===String(active)}">${e(label)}</button>`;
const select = (key,label,items,value) => `<label class="tool-field">${e(label)}<select data-pick="${key}">${items.map(([id,name])=>`<option value="${e(id)}" ${id===value?'selected':''}>${e(name)}</option>`).join('')}</select></label>`;
const flag = t => `<span class="gov-status s-${t.status}">${statuses[t.status]}</span>`;
const empty = label => `<p class="gov-empty">${e(label)}</p>`;
const money = n => new Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY'}).format(n/100);
const title = (name,sub,right='')=>`<header class="desk-title"><div><h1>${e(name)}</h1><p>${e(sub)}</p></div>${right}</header>`;
const box = (name,content,right='')=>`<section class="c-box"><header><h2>${e(name)}</h2>${right}</header>${content}</section>`;
const sectionLabel = (name,small)=>`<div class="section-label"><h2>${e(name)}</h2><small>${e(small)}</small></div>`;
const today = () => localDate();
const inOrder = (state, id) => state.tasks.filter(t=>t.orderId===id);
const statusGroup = t => ['complete','archived'].includes(t.status)?'settled':t.deadline<today()?'late':t.deadline<=localDate(3)?'soon':'normal';
const getOrder = (s,t) => s.orders.find(o=>o.id===t.orderId);
function taskRows(s, tasks, none='当前条件下没有事项。') {
  return tasks.length?`<ul class="case-list">${tasks.map(t=>`<li><a href="${href('tasks',t.id)}"><div><small>${e(t.orderId)} · ${e(getOrder(s,t).customer)}</small><b>${e(t.title)}</b></div>${flag(t)}<time>${e(t.deadline)}</time><i aria-hidden="true">↗</i></a></li>`).join('')}</ul>`:empty(none);
}
function orderPick(s,p) {
  const order=s.orders.find(o=>o.id===p.order)||s.orders[0];
  return {order,control:select('order','服务订单',s.orders.map(o=>[o.id,o.customer+' · '+o.title]),order.id)};
}
function taskPick(s,p,choices) {
  const task=choices.find(t=>t.id===p.task)||choices[0];
  return {task,control:task?select('task','选择事项',choices.map(t=>[t.id,t.title+' · '+t.orderId]),task.id):''};
}
function fieldMap(v) {
  const m=new Map([['作业说明',v.summary],['材料索引',v.evidence]]);
  for(const p of v.projects||[]) m.set('项目 '+p.id,[p.name,p.person,p.start+' 至 '+p.end,money(p.budget)].join(' · '));
  for(const f of v.fees||[]) m.set('明细 '+f.id,[f.projectId,f.category,f.period,f.voucher,money(f.amount)].join(' · '));
  return m;
}
function compare(t,p,forced) {
  if(!t.versions.length) return empty('首次提交后可查看底稿版本。');
  const end=forced ?? Math.min(t.versions.length-1,Math.max(0,Number(p.version??t.versions.length-1)||0));
  const prior=end?fieldMap(t.versions[end-1]):new Map();
  const current=fieldMap(t.versions[end]);
  const only=p.diff!=='all' && end>0;
  const all=[...new Set([...prior.keys(),...current.keys()])];
  const keys=all.filter(k=>!only||prior.get(k)!==current.get(k));
  const controls=forced===undefined?select('version','提交版本',t.versions.map((_,i)=>[String(i),'V'+(i+1)]),String(end)):'';
  return `<div class="doc-tools">${controls}<div class="picks">${tab('diff','all','全部字段',only?'changed':'all')}${tab('diff','changed','仅看变化',only?'changed':'all')}</div></div>
    <div class="diff-grid"><div class="diff-heading"><b>${end?'上一版 V'+end:'初次提交'}</b><b>本版 V${end+1}</b></div>${keys.map(k=>`<article class="diff-line ${prior.get(k)!==current.get(k)?'changed':''}"><h3>${e(k)}</h3><div><span>${e(prior.get(k)||'—')}</span><span>${e(current.get(k)||'—')}</span></div></article>`).join('')||empty('两版字段相同。')}</div>`;
}
function history(t) {
  return `<ol class="record-log">${[...t.history].reverse().map(ev=>`<li><b>${e(ev.label)}</b><small>${e(roles[ev.role])} · ${e(new Date(ev.at).toLocaleString('zh-CN',{hour12:false}))}</small>${ev.note?`<p>${e(ev.note)}</p>`:''}</li>`).join('')}</ol>`;
}
const home = {
  hall(s,p) {
    const q=(p.query||'').trim().toLowerCase(), scope=p.scope||'all';
    const matches=s.tasks.filter(t=>(scope==='all'||t.line===scope)&&[t.title,t.orderId,getOrder(s,t).customer].some(v=>v.toLowerCase().includes(q)));
    return `<section class="hall-hero"><div><p class="domain-label">科研项目与财税服务</p><h1>综合办事大厅</h1><form class="hall-search" data-search><label class="sr-only" for="lookup">检索事项</label><input id="lookup" name="query" type="search" maxlength="120" value="${e(q)}" placeholder="输入事项名称、客户或订单编号"><button>查询事项</button></form></div></section>
      <div class="hall-body"><section>${sectionLabel(q?'检索结果':'办理事项',matches.length+' 项')}<div class="picks">${[['all','全部'],['research','科研服务'],['finance','财税服务']].map(([v,l])=>tab('scope',v,l,scope)).join('')}</div>${taskRows(s,matches)}</section>
      <aside class="service-index"><h2>业务入口</h2>${[['客户与订单','orders'],['研发项目台账','projects'],['交付成果归档','archive']].map(([l,k])=>link(l,k)).join('')}</aside></div>`;
  },
  intake(s,p,role) {
    const {order,control}=orderPick(s,p), kind=p.kind==='finance'?'finance':'research', step=Number(p.step||1);
    const kinds={research:'科研立项',finance:'费用归集'};
    const body=step===1?`<h2>选取服务订单</h2>${control}<section class="intake-ticket"><header><small>受理联</small><strong>${e(order.id)}</strong></header><h3>${e(order.customer)}</h3><dl><dt>合同编号</dt><dd>${e(order.contract)}</dd><dt>受理期限</dt><dd>${e(order.deadline)}</dd></dl></section>${tab('step',2,'继续选择事项 →',0)}`:
    step===2?`<h2>选择受理事项</h2><div class="choice-tiles">${Object.entries(kinds).map(([k,l])=>tab('kind',k,l,kind)).join('')}</div><p>任务将分派至${kind==='research'?'科研':'财务'}承办岗位。</p>${tab('step',3,'核对派单信息 →',0)}`:
    `<h2>核对派单信息</h2><dl class="facts"><dt>服务客户</dt><dd>${e(order.customer)}</dd><dt>订单</dt><dd>${e(order.id)}</dd><dt>受理事项</dt><dd>${kinds[kind]}</dd><dt>截止日期</dt><dd>${e(order.deadline)}</dd></dl>
      ${role==='dispatcher'?`<button class="cta" data-command="assign" data-id="${e(order.id)}" data-kind="${kind}">填写并派发任务</button>`:'<p>切换为派单经理后可派发任务。</p>'}`;
    return title('一窗受理台','根据委托订单发起办理')+`<div class="intake-layout"><aside class="step-rail">${['服务订单','受理事项','核对派单'].map((l,i)=>tab('step',i+1,'0'+(i+1)+'　'+l,step)).join('')}</aside><section class="intake-form">${body}</section><aside class="intake-side"><small>订单内已派</small><strong>${inOrder(s,order.id).length}</strong><h2>关联事项</h2>${taskRows(s,inOrder(s,order.id))}</aside></div>`;
  },
  review(s,p,role) {
    const choices=[...s.tasks].sort((a,b)=>b.versions.length-a.versions.length);
    const {task:t,control}=taskPick(s,p,choices);
    const last=[...t.history].reverse().find(ev=>ev.note);
    return title('联合会审室','比对提交底稿，核对修改依据',control)+`<div class="review-layout"><section class="proof-doc"><div class="doc-mast"><small>${e(t.orderId)}</small><h2>${e(t.title)}</h2>${flag(t)}</div>${compare(t,p)}</section>
      <aside class="review-notes"><h2>会审意见</h2>${last?`<blockquote>${e(last.note)}<cite>${roles[last.role]} · ${e(last.label)}</cite></blockquote>`:empty('暂无书面意见。')}${link('查看完整底稿','tasks',t.id)}${actionsFor(t,role,s).filter(k=>['approve','return'].includes(k)).map(k=>`<button class="cta" data-command="${k}" data-id="${e(t.id)}">${actionLabels[k]}</button>`).join('')}</aside></div>`;
  },
  archive(s,p) {
    const list=s.tasks.filter(t=>t.status==='archived'), {task:t,control}=taskPick(s,p,list);
    if(!t) return title('公文案卷馆','科研财税服务交付卷宗')+empty('归档后可在这里查阅成果。');
    const mode=p.leaf||'catalog', o=getOrder(s,t);
    return title('公文案卷馆','已归档成果检索与调阅',control)+`<div class="archive-layout"><aside class="folio-cover"><small>科研财税业务档案</small><h2>交付案卷</h2><div>${e(o.customer)}</div><span>${e(o.id)}</span><b>归 档</b></aside><section class="folio-pages"><small>${e(o.contract)}　/　${e(o.year)} 年度</small><h2>${e(t.title)}</h2><div class="picks">${[['catalog','材料目录'],['log','办理记录'],['versions','版本索引']].map(([k,l])=>tab('leaf',k,l,mode)).join('')}</div>${mode==='log'?history(t):mode==='versions'?`<ol class="folio-list">${t.versions.map((v,i)=>`<li><b>V${i+1}</b>　${e(v.summary)}</li>`).join('')}</ol>`:`<dl class="facts"><dt>材料索引</dt><dd>${e(t.draft.evidence)}</dd><dt>底稿摘要</dt><dd>${e(t.draft.summary)}</dd><dt>客户确认</dt><dd>${e(t.history.findLast(ev=>ev.label===actionLabels.confirm)?.note||'已登记')}</dd></dl>`}<button class="cta" data-command="export" data-id="${e(t.id)}">下载归档记录 ↓</button></section></div>`;
  },
  calendar(s,p) {
    const base=new Date(today()+'T12:00:00');base.setDate(1);base.setMonth(base.getMonth()+Number(p.month||0));
    const y=base.getFullYear(),m=base.getMonth(),days=new Date(y,m+1,0).getDate();
    const prefix=y+'-'+String(m+1).padStart(2,'0'), monthRows=s.tasks.filter(t=>t.deadline.startsWith(prefix));
    const date=p.day?.startsWith(prefix)?p.day:'';
    const cells=Array.from({length:(base.getDay()+6)%7},()=>'<i></i>');
    for(let i=1;i<=days;i++){const d=prefix+'-'+String(i).padStart(2,'0'),num=monthRows.filter(t=>t.deadline===d).length;cells.push(`<button class="cal-day" ${d===today()?'aria-current="date"':''} data-set="day" data-value="${d}" aria-label="${d}，${num}项" aria-pressed="${date===d}"><b>${i}</b>${num?`<small>${num} 项</small>`:''}</button>`);}
    return title('督办日历','按办理期限排查事项')+`<div class="cal-layout"><section class="month-sheet"><header>${tab('month',Number(p.month||0)-1,'上月',NaN)}<h2>${y} 年 <b>${m+1}</b> 月</h2><div class="month-actions">${tab('today',today(),'今天',NaN)}${tab('month',Number(p.month||0)+1,'下月',NaN)}</div></header><div class="cal-grid">${[...'一二三四五六日'].map(x=>`<strong>${x}</strong>`).join('')}${cells.join('')}</div></section><aside class="day-agenda"><small>办理日程</small><h2>${date||'本月事项'}</h2>${date?tab('day','','看整月','x'):''}${taskRows(s,date?monthRows.filter(t=>t.deadline===date):monthRows)}</aside></div>`;
  },
  funds(s,p) {
    const {order,control}=orderPick(s,p);
    const projects=projectsFor(s,order.id), project=projects.find(x=>x.id===p.project)||projects[0];
    const fees=inOrder(s,order.id).filter(t=>t.line==='finance').flatMap(t=>t.draft.fees.map(row=>({...row,task:t.id})));
    const rows=fees.filter(f=>f.projectId===project?.id), total=rows.reduce((n,f)=>n+f.amount,0), mode=p.pivot||'voucher';
    const cats=new Map();for(const f of rows)cats.set(f.category,(cats.get(f.category)||0)+f.amount);
    const budget=project?.budget||0;
    const ratio=budget?total/budget:0;
    const meter=budget?`<div class="budget-meter"><div><span>底稿登记额占预算</span><b>${(ratio*100).toLocaleString('zh-CN',{maximumFractionDigits:1})}%</b></div><i style="--share:${Math.min(100,ratio*100)}%" aria-hidden="true"></i></div>`:'';
    const entries=mode==='category'?[...cats].map(([label,n])=>[label,money(n)]):rows.map(f=>[f.voucher+' · '+f.category,money(f.amount),f.task]);
    return title('资金核验台','按订单核对项目预算与底稿登记额',control)+`<div class="fund-layout"><aside class="project-rail"><h2>项目索引</h2>${projects.map(pr=>tab('project',pr.id,pr.id+'　'+pr.name,project?.id)).join('')||empty('暂无通过内部审核的项目。')}</aside><section class="fund-sheet"><small>${e(project?.id||order.id)}</small><h2>${e(project?.name||'等待立项清单')}</h2><div class="fund-totals"><div><small>已批项目预算</small><b>${money(project?.budget||0)}</b></div><div><small>底稿登记额</small><b>${money(total)}</b></div></div>${meter}<div class="picks">${tab('pivot','voucher','凭证明细',mode)}${tab('pivot','category','按类别汇总',mode)}</div><ul class="amount-list">${entries.map(([l,a,id])=>`<li>${id?link(l,'tasks',id):e(l)}<b>${a}</b></li>`).join('')}</ul>${entries.length?'':empty('当前项目尚无费用明细。')}</section></div>`;
  },
  liaison(s,p,role) {
    const {order,control}=orderPick(s,p), tasks=inOrder(s,order.id);
    const mode=p.issues||'open';
    const issues=tasks.flatMap(t=>t.issues.map(i=>({...i,task:t}))).filter(i=>mode==='all'||!i.closed);
    return title('双线协办室','科研立项与财务归集按同一订单交接',control)+`<div class="lane-grid">${[['research','科研办理线'],['finance','财务办理线']].map(([k,l])=>`<section class="lane lane-${k}"><div><small>${e(order.id)}</small><h2>${l}</h2></div>${taskRows(s,tasks.filter(t=>t.line===k))}</section>`).join('')}</div>`+
      box('跨线补件',`<div class="picks">${tab('issues','open','待闭环',mode)}${tab('issues','all','全部记录',mode)}</div>${issues.map(i=>`<div class="issue-row"><b>${e(i.question)}</b><span>${e(i.reply||'等待科研补充')}</span>${!i.closed && role==='research' && !i.reply ? `<button class="cta" data-command="reply" data-id="${e(i.task.id)}" data-row="${e(i.id)}">回复补件</button>` : (!i.closed && i.reply && editable(i.task,role) ? `<button class="cta" data-command="close-issue" data-id="${e(i.task.id)}" data-row="${e(i.id)}">确认关闭</button>` : link('进入处理','tasks',i.task.id))}</div>`).join('')||empty(mode==='open'?'当前订单没有待闭环补件。':'当前订单暂无补件记录。')}`);
  },
  guide(s,p) {
    const guides={
      research:['科研立项','立项会议材料、项目负责人、研发周期及预算。','登记项目和材料索引，逐级审核；重大事项由总监终审。','记录客户确认后归档，已完成内审的项目可供财务引用。'],
      finance:['费用归集','同一订单已通过内部审核的项目清单、凭证及期间。','按实际发生额录入费用，缺项发起补件，关闭问题后提交。','留存各提交版本、凭证索引、审核意见与客户确认记录。'],
      close:['交付归档','准备通过内部末级审核的底稿和客户签收说明。','派单经理登记确认或修改意见，修改后重新履行审核。','归档后可下载含版本和处理记录的 JSON。'],
    };
    const key=Object.hasOwn(guides,p.service)?p.service:'research', step=Number(p.chapter||1), g=guides[key];
    return title('事项导办册','按办理情形查阅材料与作业要求')+`<div class="guide-layout"><aside><h2>事项目录</h2>${Object.entries(guides).map(([k,v])=>tab('service',k,v[0],key)).join('')}</aside><article class="guide-paper"><small>科研财税服务　/　办理指南</small><h2>${g[0]}</h2><div class="picks">${['材料准备','办理流程','交付成果'].map((v,i)=>tab('chapter',i+1,v,step)).join('')}</div><div class="chapter"><b>0${step}</b><p>${g[step]}</p></div>${key==='close'?link('查阅已归档成果','archive'):link('进入对应任务','tasks',key)}</article></div>`;
  },
  monitor(s,p) {
    const groups={all:'全部事项',late:'已超期',soon:'三日内到期',normal:'正常在办',settled:'已完成 / 归档'}, k=Object.hasOwn(groups,p.risk)?p.risk:'all';
    const counts=Object.fromEntries(Object.keys(groups).map(g=>[g,s.tasks.filter(t=>g==='all'||statusGroup(t)===g).length]));
    const rows=s.tasks.filter(t=>k==='all'||statusGroup(t)===k).sort((a,b)=>a.deadline.localeCompare(b.deadline));
    const colors={late:'#ebac97',soon:'#ebcb80',normal:'#75cdd1',settled:'#8eaecc'};
    let edge=0;
    const arcs=Object.entries(colors).filter(([key])=>counts[key]).map(([key,color])=>{
      const start=edge;
      edge+=counts[key]*100/s.tasks.length;
      return (k==='all'||k===key?color:'#315063')+' '+start+'% '+edge+'%';
    });
    const ring=arcs.length?'conic-gradient('+arcs.join(', ')+')':'#315063';
    return title('运行指挥屏','科研财税服务事项运行态势')+`<div class="monitor-grid"><aside class="monitor-total"><div class="status-dial" style="--arcs:${ring}"><span><strong>${String(counts[k]).padStart(2,'0')}</strong><small>${k==='all'?'在册办理事项':groups[k]}</small></span></div>${tab('risk','all','查看全部',k)}</aside><section class="bands">${Object.keys(groups).slice(1).map(g=>`<button data-set="risk" data-value="${g}" aria-pressed="${g===k}"><span>${groups[g]}</span><i><u style="--band:${colors[g]};width:${100*counts[g]/Math.max(1,s.tasks.length)}%"></u></i><b>${counts[g]}</b></button>`).join('')}</section></div>`+box(groups[k],taskRows(s,rows),'按截止日期排序');
  },
  access(s,p,role) {
    const choices={mine:'办理我的待办',check:'查询审核事项',archive:'查找交付档案'},k=Object.hasOwn(choices,p.intent)?p.intent:'mine';
    const rows=s.tasks.filter(t=>k==='mine'?actionsFor(t,role,s).length:k==='archive'?t.status==='archived':['lead','reviewer','director'].includes(t.status));
    return `<section class="access-page ${p.size==='large'?'enlarged':''}">${title('大字办事窗口','选择本次要办的事项',`<div class="picks">${tab('size','base','标准字号',p.size||'base')}${tab('size','large','放大字号',p.size||'base')}</div>`)}
      <div class="intent-grid">${Object.entries(choices).map(([id,l])=>tab('intent',id,l,k)).join('')}</div>${sectionLabel(choices[k],rows.length+' 项')}${taskRows(s,rows)}</section>`;
  },
};

export function workspace(ui,state,p,role){return home[ui](state,p,role);}
export function inspector(ui,t,p,index) {
  const label=ui==='review'?'版本比对':'案卷速览', mode=p.inspect|| (ui==='review'?'diff':'card');
  return `<details class="inspector" ${p.expanded?'open':''}><summary>${label}　<span>${e(t.orderId)}</span></summary><div class="picks">${[['card','事项信息'],['diff','版本比对'],['history','流转记录']].map(([k,l])=>tab('inspect',k,l,mode)).join('')}</div>${mode==='diff'?compare(t,p,index??undefined):mode==='history'?history(t):`<dl class="facts"><dt>当前节点</dt><dd>${verdicts[t.status]}</dd><dt>办结期限</dt><dd>${e(t.deadline)}</dd><dt>材料索引</dt><dd>${e((t.versions[index]||t.draft).evidence||'待填写')}</dd></dl>`}</details>`;
}
export function gallery(p) {
  const ids=Object.keys(designs), comparison=p.gallery==='pair';
  const card=id=>`<a class="design-card" href="?ui=${id}#dashboard"><img src="./previews/${id}.webp" width="640" height="400" alt="${designs[id][0]}实际界面"><div><small>${designs[id][1]}</small><h2>${designs[id][0]}</h2><p>${designs[id][2]}</p><b>进入体验 ↗</b></div></a>`;
  const both=[p.left||'hall',p.right||'review'];
  return title('政务界面展廊','十套可操作的科研财税工作台，共用本浏览器的演示业务数据。')+
    `<div class="gallery-tools picks">${tab('gallery','all','全部方案',comparison?'pair':'all')}${tab('gallery','pair','两案并排对照',comparison?'pair':'all')}</div>`+
    (comparison?`<p class="trial-note">左右两侧均可直接操作。每侧独立试办，切换该侧方案后重新开始。</p>
      <div class="pair-gallery">${both.map((id,i)=>`<section><header>${select(i?'right':'left',i?'右侧方案':'左侧方案',ids.map(k=>[k,designs[k][0]]),id)}<a class="c-link" href="?ui=${id}#dashboard">进入完整版 ↗</a></header><iframe title="${designs[id][0]}独立试办区" src="?ui=${id}&amp;trial=1#dashboard"></iframe></section>`).join('')}</div>`:
    `<div class="design-grid">${ids.map(card).join('')}</div>`);
}
