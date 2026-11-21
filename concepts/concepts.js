import { initialState, statuses } from '../model.js?v=classic';
import { drawPlate, drawRoutes } from './draw.js';

const views = {
  folio: ['委托案卷', '翻动卷宗标签，查看一个客户的项目和在办任务。'],
  signal: ['双线调度', '沿科研线和财务线选节点，找出交接处的待办。'],
  ledger: ['费用分账', '在项目和科目之间切换，追溯每笔费用的凭证。'],
  week: ['交付周历', '翻周、选日期，把截止日变成当天的工作清单。'],
  proof: ['底稿校阅', '并排核对两次提交，点批注定位预算修改。'],
};
const keys = Object.keys(views);
const view = new URLSearchParams(location.search).get('view');
const screen = document.querySelector('#screen');
const state = initialState();
const [first, second] = state.orders;
const [finance, revision, research, , supplement] = state.tasks;
const nameOf = order => order.customer.replace('（示例）', '');
const tasksOf = order => state.tasks.filter(task => task.orderId === order.id);
const orderOf = task => state.orders.find(order => order.id === task.orderId);
const detail = (task, label = '查看任务') => `<a class="detail" href="../#tasks/${encodeURIComponent(task.id)}">${label} <span aria-hidden="true">↗</span></a>`;
const money = cents => (cents / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const shortDate = iso => iso.slice(5).replace('-', '.');
const dateKey = date => [date.getFullYear(), String(date.getMonth()+1).padStart(2,'0'), String(date.getDate()).padStart(2,'0')].join('-');
const addDays = (date,n) => new Date(date.getFullYear(), date.getMonth(), date.getDate()+n, 12);
const monday = date => addDays(date, -((date.getDay()+6)%7));
const today = new Date();
let orderIndex = 0, station = 1, grouping = 'project', groupIndex = 0, annotation = 'budget', proofMode = 'compare';
let selectedDate = finance.deadline, start = monday(new Date(selectedDate+'T12:00:00'));

function shell() {
  return `<header class="mast"><a class="identity" href="./"><i class="symbol" aria-hidden="true"></i>科研财税协同</a>
    <nav aria-label="参考方案导航"><a href="./">五案总览</a><span class="divider"></span><a href="?view=${keys[(keys.indexOf(view)+1)%keys.length]}">下一方案 <span aria-hidden="true">→</span></a></nav></header>`;
}
function gallery() {
  return `<div class="gallery-wrap"><header class="gallery-nav"><span class="identity"><i class="symbol" aria-hidden="true"></i>科研财税协同</span><a href="../">打开现有工作台 ↗</a></header>
    <div class="gallery-heading"><div><p class="kicker">研发服务工作台</p><h1>五种工作界面</h1></div><p>同一组示例业务，五种办理方式。<br>选择一张预览，试用其中的交互。</p></div>
    <div class="gallery-grid">${keys.map((key,i)=>`<a class="cover cover-${key}" href="?view=${key}"><div class="cover-img"><img src="preview/${key}.webp" alt="${views[key][0]}工作台界面"></div>
      <div class="cover-caption"><span class="cover-no">0${i+1}</span><div><h2>${views[key][0]}</h2><p>${views[key][1]}</p></div><span class="round-arrow" aria-hidden="true">↗</span></div></a>`).join('')}</div></div>`;
}
function folio() {
  const order = state.orders[orderIndex];
  const tasks = tasksOf(order);
  const projects = tasks.find(t=>t.line==='research')?.draft.projects || [];
  return `<div class="folio-title"><div><p class="kicker">客户与订单 / 卷宗目录</p><h1>委托案卷<span>。</span></h1></div><div class="yearmark"><small>服务年度</small><strong>${order.year}</strong></div></div>
    <div class="folio-cabinet"><nav class="folder-tabs" aria-label="选择客户案卷">${state.orders.map((o,i)=>`<button data-order="${i}" aria-pressed="${orderIndex===i}"><span>${o.id.slice(-3)}</span>${nameOf(o)}</button>`).join('')}</nav>
    <article class="folder-sheet"><div class="folder-document"><div class="folder-meta"><span>委托事项</span><b>${order.id}</b></div><h2>${order.title}</h2><p>${nameOf(order)}</p>
      <dl class="file-dl"><div><dt>合同编号</dt><dd>${order.contract}</dd></div><div><dt>交付期限</dt><dd>${order.deadline}</dd></div></dl><a class="folder-open" href="../#orders/${order.id}">打开订单 <span aria-hidden="true">↗</span></a></div>
      <figure class="plate"><canvas id="plate" aria-hidden="true"></canvas><figcaption>${projects.map(p=>p.id).join(' / ')} · 项目示意</figcaption></figure></article></div>
    <div class="folio-list"><h3>卷内任务 <small>${String(tasks.length).padStart(2,'0')}</small></h3>${tasks.map(t=>`<a href="../#tasks/${t.id}"><span>${t.line==='research'?'科研':'财务'}</span><strong>${t.title}</strong><em>${statuses[t.status]}</em><b>↗</b></a>`).join('')}</div>`;
}
const stations = [
  { title:'立项清单', short:'科研立项', task:research, status:'已内审', x:24, y:24, note:'两个项目已通过内部末级审核，可供同单财务任务引用。' },
  { title:'费用归集', short:'财务接件', task:finance, status:statuses[finance.status], x:52, y:68, note:'已有三笔示例费用。承办人接件后，可按项目核对费用和凭证索引。' },
  { title:'补件核对', short:'两线补件', task:supplement, status:'待科研回复', x:76, y:40, note:supplement.issues[0].question },
];
function signal() {
  const selected = stations[station];
  return `<div class="signal-head"><div><p class="kicker"><i class="live-dot"></i> 科研与财务协同</p><h1>双线调度</h1></div><div class="signal-id">${first.id}<br><small>${nameOf(first)}</small></div></div>
    <section class="route-board"><div class="route-labels"><span><i></i>科研线</span><span><i></i>财务线</span></div>
      <div id="route-map"><canvas id="routes" aria-hidden="true"></canvas>${stations.map((s,i)=>`<button class="station s${i}" style="--x:${s.x}%;--y:${s.y}%" data-station="${i}" aria-pressed="${i===station}"><i></i><span>${s.title}</span></button>`).join('')}</div>
      <div class="route-caption"><span>协同节点图</span><span>● 可选择节点</span></div></section>
    <section class="station-detail"><div class="station-index"><small>当前节点</small><b>0${station+1}</b></div><div><p class="kicker">${selected.short} / ${selected.status}</p><h2>${selected.task.title}</h2><p>${selected.note}</p></div>${detail(selected.task,'进入任务')}</section>`;
}
function ledger() {
  const projects = research.draft.projects;
  const grouped = new Map();
  for (const fee of finance.draft.fees) {
    const key = grouping==='project' ? fee.projectId : fee.category;
    if (!grouped.has(key)) grouped.set(key, { key, rows:[], total:0, label:grouping==='project'?projects.find(p=>p.id===key).name:key });
    const g = grouped.get(key); g.rows.push(fee); g.total+=fee.amount;
  }
  const groups=[...grouped.values()], active=groups[groupIndex], total=groups.reduce((a,g)=>a+g.total,0);
  return `<div class="ledger-head"><div><p class="kicker">财务作业 / ${finance.draft.fees[0].period}</p><h1>费用分账</h1></div><span>${nameOf(first)}<small>${first.id}</small></span></div>
    <div class="ledger-body"><section class="sum-sheet"><p class="kicker">本期归集总额</p><p class="hero-sum"><small>¥</small>${money(total).split('.')[0]}<em>.${money(total).split('.')[1]}</em></p>
    <div class="sum-bar" aria-label="分组占比">${groups.map((g,i)=>`<button data-group="${i}" class="tone${i}" style="flex:${g.total}" aria-label="${g.label}占比${(100*g.total/total).toFixed(1)}%" aria-pressed="${groupIndex===i}"></button>`).join('')}</div>
    <div class="sum-key">${groups.map((g,i)=>`<span><i class="tone${i}"></i>${grouping==='project'?g.key:g.label} · ${(100*g.total/total).toFixed(1)}%</span>`).join('')}</div>
    <div class="ledger-controls"><h2>归集分布</h2><div class="switch">${[['project','按项目'],['category','按费用类别']].map(([k,v])=>`<button data-grouping="${k}" aria-pressed="${grouping===k}">${v}</button>`).join('')}</div></div>
    <div class="account-list">${groups.map((g,i)=>`<button data-group="${i}" aria-pressed="${i===groupIndex}"><span><small>${grouping==='project'?g.key:g.rows.length+' 笔凭证'}</small>${g.label}</span><b>${money(g.total)} <i>↘</i></b></button>`).join('')}</div></section>
    <aside class="receipt"><span class="receipt-title">凭证摘录</span><div class="receipt-top"><span>${finance.draft.fees[0].period.replace('-',' / ')}</span><span>人民币 · 元</span></div><h3>${active.label}</h3>
      <div class="voucher-list">${active.rows.map(f=>`<div><span>${f.voucher}<small>${grouping==='project'?f.category:f.projectId}</small></span><b>${money(f.amount)}</b></div>`).join('')}</div><div class="receipt-total"><span>小计</span><b>${money(active.total)}</b></div>${detail(finance,'打开费用底稿')}</aside></div>`;
}
const weekdays = '一二三四五六日';
function week() {
  const days=Array.from({length:7},(_,i)=>addDays(start,i));
  const active=new Date(selectedDate+'T12:00:00'), due=state.tasks.filter(t=>t.deadline===selectedDate);
  const monthName = new Intl.DateTimeFormat('zh-CN',{month:'long'}).format(active);
  return `<div class="week-head"><div><p class="kicker">办理期限 / ${active.getFullYear()} 年</p><h1>交付周历</h1></div><div class="week-controls"><button data-week="-1" aria-label="上一周">←</button><button data-today>本周</button><button data-week="1" aria-label="下一周">→</button></div></div>
    <section class="week-board"><div class="month-cover"><div class="binding" aria-hidden="true"><i></i><i></i><i></i></div><span>${monthName} / 周${weekdays[(active.getDay()+6)%7]}</span><strong>${String(active.getDate()).padStart(2,'0')}</strong><small>${selectedDate}</small></div>
    <div class="week-sheet"><div class="week-range"><b>七日排期</b><span>${shortDate(dateKey(days[0]))} — ${shortDate(dateKey(days[6]))}</span></div>
    <div class="day-strip">${days.map((d,i)=>{const iso=dateKey(d), count=state.tasks.filter(t=>t.deadline===iso).length;return `<button data-date="${iso}" aria-label="${iso}，${count}项截止" aria-pressed="${iso===selectedDate}"><span>周${weekdays[i]}</span><b>${String(d.getDate()).padStart(2,'0')}</b><i class="${count?'marked':''}"></i></button>`}).join('')}</div>
    <h2>当日截止 <small>${due.length} 项</small></h2><div class="day-agenda">${due.length?due.map(t=>`<a href="../#tasks/${t.id}"><span class="line-mark"></span><div><strong>${t.title}</strong><small>${nameOf(orderOf(t))} · ${statuses[t.status]}</small></div><b>↗</b></a>`).join(''):'<p>当天没有到期任务。</p>'}</div></div></section>
    <section class="next-dates"><h3>其他截止日</h3>${[...new Set(state.tasks.map(t=>t.deadline))].sort().filter(d=>d!==selectedDate).map(d=>`<button data-jump="${d}">${shortDate(d)} <span>${state.tasks.find(t=>t.deadline===d).title}</span> ↗</button>`).join('')}</section>`;
}
const before=revision.versions[0], after=revision.versions[1];
const annotations = {
  budget:{label:'项目预算', note:revision.history.find(e=>e.label==='退回修改').note, old:'原预算', fresh:'修订预算'},
  evidence:{label:'证明材料', note:'核对新提交的试验方案和检测报价是否已列入材料索引。', old:'原材料索引', fresh:'修订材料索引'},
};
function proof() {
  const a=annotations[annotation];
  const val=(v)=>annotation==='budget' ? `<b class="proof-number">${v.projects[0].budget/1000000}</b> 万元` : v.evidence;
  return `<div class="proof-head"><div><p class="kicker">科研线 / 经理复审</p><h1>底稿校阅</h1></div><div class="mode-switch">${[['compare','版本对照'],['current','仅看 V2']].map(([id,text])=>`<button data-mode="${id}" aria-pressed="${proofMode===id}">${text}</button>`).join('')}</div></div>
   <div class="proof-desk"><section class="proof-paper"><header class="paper-meta"><b>研发立项底稿</b><span>${after.projects[0].id} / V2</span></header>
    <h2>${after.projects[0].name}</h2><p class="byline">${nameOf(second)}　·　负责人 ${after.projects[0].person}</p><h3>本次提交说明</h3>
    <p class="manuscript">研发预算调整为<button data-note="budget" aria-pressed="${annotation==='budget'}">22 万元<sup>1</sup></button>，已补入低温耐磨试验的检测费用。</p>
    <h3>材料索引</h3><p class="manuscript">立项会议纪要；<button data-note="evidence" aria-pressed="${annotation==='evidence'}">低温试验方案与检测报价<sup>2</sup></button>。</p>
    <div class="paper-foot"><span>${second.id}</span><span>1 / 1</span></div></section>
    <aside class="margin-notes"><p class="kicker">校阅批注 / ${annotation==='budget'?'01':'02'}</p><h2>${a.label}</h2><p class="note-text">${a.note}</p><div class="diff">${proofMode==='compare'?`<div class="old"><small>V1 · ${a.old}</small><p>${val(before)}</p></div>`:''}<div class="new"><small>V2 · ${a.fresh}</small><p>${val(after)}</p></div></div>${detail(revision,'查看审核记录')}</aside></div>`;
}
function render() {
  if (!keys.includes(view)) {
    document.body.className='gallery'; screen.innerHTML=gallery(); return;
  }
  document.body.className=view;
  document.title=views[view][0]+' · 工作台设计参考';
  screen.innerHTML=shell()+`<div class="workspace">${({folio,signal,ledger,week,proof})[view]()}</div><footer class="foot"><span>交互参考稿 · 虚构业务数据</span><a href="../">进入现有工作台 ↗</a></footer>`;
  redraw();
}
function redraw(){
  if(view==='folio') drawPlate(document.querySelector('#plate'),orderIndex);
  if(view==='signal') drawRoutes(document.querySelector('#routes'));
}
screen.addEventListener('click',e=>{
  const b=e.target.closest('button');
  if(!b)return;
  const d=b.dataset;
  if('order' in d) orderIndex=Number(d.order);
  else if('station' in d) station=Number(d.station);
  else if('grouping' in d) { grouping=d.grouping; groupIndex=0; }
  else if('group' in d) groupIndex=Number(d.group);
  else if('date' in d) selectedDate=d.date;
  else if('jump' in d) { selectedDate=d.jump; start=monday(new Date(selectedDate+'T12:00:00')); }
  else if('week' in d) { start=addDays(start,7*Number(d.week)); selectedDate=dateKey(addDays(new Date(selectedDate+'T12:00:00'),7*Number(d.week))); }
  else if('today' in d) { start=monday(today); selectedDate=dateKey(today); }
  else if('mode' in d) proofMode=d.mode;
  else if('note' in d) annotation=d.note;
  else return;
  const key=Object.keys(d)[0], oldButtons=[...screen.querySelectorAll('button')].filter(x=>x.dataset[key]===d[key]), match=oldButtons.indexOf(b);
  render();
  const buttons=[...screen.querySelectorAll('button')].filter(x=>x.dataset[key]===d[key]);
  const focusTarget=buttons[match] || (view==='week'?screen.querySelector('.day-strip [aria-pressed="true"]'):null);
  focusTarget?.focus({preventScroll:true});
});
window.addEventListener('resize',redraw);
render();
