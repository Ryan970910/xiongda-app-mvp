import { actionsFor, actionLabels, editable, localDate, projectsFor, roles, statuses } from './model.js';
import {
  concepts,
  safe as e,
  target,
  openRecord as go,
  art,
  pick,
  select,
  source,
  yen,
  serial,
  empty,
  at,
  steps
} from './themes.js';
const orderOf = (state, task) => state.orders.find((order) => order.id === task.orderId);
const artKeys = ['specimen', 'optic', 'folio', 'print', 'court', 'ridge'];
const sheets = ['print', 'raster', 'folio', 'optic', 'specimen', 'court'];
const caption = (kicker, heading, body = '') =>
  `<header class="scene-title"><p>${kicker}</p><h1>${heading}</h1>${body ? `<div>${body}</div>` : ''}</header>`;
const taskLink = (t) => go('打开事项', 'tasks', t.id);
const action = (cmd, id, label, row = '') =>
  `<button class="do" data-command="${cmd}" data-id="${e(id)}" data-row="${e(row)}">${e(label)} ↗</button>`;
function actions(t, role, state, allowed) {
  return actionsFor(t, role, state)
    .filter((cmd) => allowed.includes(cmd))
    .map((cmd) => action(cmd, t.id, actionLabels[cmd]))
    .join('');
}
function specimen(s, p) {
  const projects = s.orders.flatMap((order) =>
    projectsFor(s, order.id).map((project) => ({ project, order }))
  );
  if (!projects.length) return empty('项目完成内部审核后，将在这里生成项目标本。');
  const index = at(p.project, projects),
    { project: j, order } = projects[index];
  const fields = [
      ['负责人', j.person],
      ['研发周期', j.start + ' — ' + j.end],
      ['项目预算', yen(j.budget)]
    ],
    point = at(p.pin, fields);
  return `<div class="atlas"><div class="atlas-intro">${caption('科研立项 / PROJECT ATLAS', '研发<br>标本台')}<p>${e(j.name)}</p>
    ${select(
      'project',
      '选择项目',
      projects.map(({ project }, i) => [i, project.id + ' · ' + project.name]),
      index
    )}</div>
    <figure class="atlas-plate">${art('specimen', '精密伺服装置分解示意，图中标注可操作')}<figcaption>研发装置示意　/　${e(j.id)}</figcaption>
      ${fields.map(([name], i) => pick('pin', i, `<b>${serial(i + 1)}</b><span>${name}</span>`, point, 'map-pin pin-' + i)).join('')}</figure>
    <div class="spec-data" aria-live="polite"><span>${serial(point + 1)} / ${fields[point][0]}</span><strong>${e(fields[point][1])}</strong>${go('所属订单', 'orders', order.id)}</div></div>`;
}
function queue(s, p, role) {
  const groups = { open: '在办', all: '全部' },
    group = p.queueScope === 'all' ? 'all' : 'open';
  const tasks = s.tasks.filter((t) => group === 'all' || !['archived', 'complete'].includes(t.status));
  const index = at(p.ticket, tasks),
    t = tasks[index];
  return `<div class="counter">${caption('委托受理 / ON CALL', '受理候场线')}
    <div class="queue-toolbar"><div>${Object.entries(groups)
      .map(([k, l]) => pick('queueScope', k, l, group))
      .join('')}</div><span>左右拖动票签</span></div>
    ${
      t
        ? `<div class="ticket-track" data-swipe="ticket" data-index="${index}" data-count="${tasks.length}">
      ${[-1, 0, 1]
        .map((offset) => {
          const n = index + offset,
            item = tasks[n];
          return item
            ? `<button class="queue-ticket offset-${offset + 1}" data-set="ticket" data-value="${n}" aria-pressed="${n === index}">
        <small>${item.line === 'finance' ? '财税作业' : '科研作业'}　/　${e(item.orderId)}</small><b>${serial(n + 1)}</b><span>${e(item.title)}</span><i>${statuses[item.status]}　·　${e(item.deadline)}</i></button>`
            : `<div class="queue-end"><small>当班票夹　/　${tasks.length} 件</small><strong>${e(orderOf(s, t).customer)}</strong><span>${e(orderOf(s, t).contract)}</span></div>`;
        })
        .join('')}</div>
      <div class="counter-controls">${steps('ticket', index, tasks.length, '上一张票', '下一张票')}<div>${actions(t, role, s, ['accept', 'approve'])}${taskLink(t)}</div></div>`
        : empty('当前没有在办事项。可切换至全部委托。')
    }</div>`;
}
function arc(s, p) {
  const orders = s.orders,
    index = at(p.reel, orders),
    order = orders[index];
  const tasks = s.tasks.filter((t) => t.orderId === order.id);
  return `<div class="exhibit">${caption('委托阅览 / COMMISSIONS', '委托陈列馆')}
    <div class="card-orbit" data-swipe="reel" data-index="${index}" data-count="${orders.length}">${orders
      .map((o, i) => {
        const d = (i - index + orders.length) % orders.length,
          offset = d > orders.length / 2 ? d - orders.length : d;
        return Math.abs(offset) <= 2
          ? `<button class="exhibit-card" style="--slot:${offset};z-index:${5 - Math.abs(offset)}" aria-pressed="${i === index}" data-set="reel" data-value="${i}">${art(artKeys[(i + 1) % artKeys.length])}<span>${e(o.id)}<b>${e(o.title)}</b></span></button>`
          : '';
      })
      .join(
        ''
      )}</div><div class="exhibit-foot">${steps('reel', index, orders.length, '上一份委托', '下一份委托')}
      <div><small>${e(order.contract)}　/　${tasks.length} 项作业</small><h2>${e(order.customer)}</h2></div>${go('展开委托', 'orders', order.id)}</div></div>`;
}
function press(s, p) {
  const docs = s.tasks.filter((t) => t.draft.evidence?.trim()),
    i = at(p.printDoc, docs),
    t = docs[i];
  return `<div class="print-shop"><div class="press-top">${caption('底稿材料 / PRINT ROOM', '材料印刷间')}<div class="pan-pad"><button data-pan="-1" aria-label="向左移动材料画布">←</button><button data-pan="up" aria-label="向上移动材料画布">↑</button><button data-pan="down" aria-label="向下移动材料画布">↓</button><button data-pan="1" aria-label="向右移动材料画布">→</button></div></div>
    ${
      t
        ? `<div class="paste-window" tabindex="0" aria-label="材料拼贴，可拖动或按四个方向键"><div class="paste-wall" style="--wall-width:${docs.length * 278 + 140}px">${docs.map((d, n) => `<button class="broadside broad-${n % 4}" style="left:${32 + 278 * n}px" data-set="printDoc" data-value="${n}" aria-pressed="${n === i}">${art(sheets[n % sheets.length])}<span>${serial(n + 1)}　/　${e(d.title)}</span></button>`).join('')}</div></div>
    <section class="print-caption"><strong>${e(t.title)}</strong><p>${e(t.draft.evidence)}</p>${taskLink(t)}</section>`
        : empty('登记底稿的材料索引后会出现材料印张。')
    }</div>`;
}
function leaves(s, p, role) {
  const tasks = s.tasks
    .filter((t) => t.versions.length)
    .sort((a, b) => b.versions.length - a.versions.length);
  const i = at(p.volume, tasks),
    t = tasks[i];
  if (!t) return empty('提交底稿后可追溯提交版本。');
  const n = at(p.leaf ?? t.versions.length - 1, t.versions),
    v = t.versions[n];
  const total =
    t.line === 'research'
      ? v.projects?.reduce((a, row) => a + row.budget, 0)
      : v.fees?.reduce((a, row) => a + row.amount, 0);
  return `<div class="reader"><div class="reader-top">${caption('提交版次 / EDITIONS', '版本手卷')}${select(
    'volume',
    '选择底稿',
    tasks.map((x, j) => [j, x.title + ' · ' + x.orderId]),
    i
  )}</div>
    <div class="open-book" data-swipe="leaf" data-count="${t.versions.length}" data-index="${n}"><figure>${art('folio', '研究园区分层纸景')}<figcaption>${e(t.orderId)}<br>${e(t.title)}</figcaption></figure>
    <article class="book-leaf" data-leaf="${n}"><small>提交版次　/　V${n + 1}</small><h2>${t.line === 'research' ? '立项底稿' : '经费底稿'}</h2><p>${e(v.summary)}</p><h3>${t.line === 'research' ? '项目预算' : '登记费用'}</h3><strong>${yen(total || 0)}</strong>
     <p>${e(v.evidence)}</p><a class="page-ref" href="${target('tasks', t.id)}/version/${n}">查阅本版全文 ↗</a>
     <button class="page-corner" aria-label="${n < t.versions.length - 1 ? '翻到下一版' : '翻到上一版'}" data-set="leaf" data-value="${n < t.versions.length - 1 ? n + 1 : Math.max(0, n - 1)}" ${t.versions.length === 1 ? 'disabled' : ''}></button></article></div>
     <div class="book-tools">${steps('leaf', n, t.versions.length, '翻到上一版', '翻到下一版')}${n === t.versions.length - 1 ? actions(t, role, s, ['approve', 'return']) : ''}</div></div>`;
}
function glyph(s, p) {
  const query = p.query || '',
    term = query.toLowerCase().trim();
  const found = s.tasks.filter((t) =>
    [t.title, t.orderId, t.draft.evidence, t.draft.summary, orderOf(s, t).customer].some((x) =>
      x?.toLowerCase().includes(term)
    )
  );
  return `<div class="type-room"><div class="type-banner">${caption('全文检索 / TYPE INDEX', '字模检索室')}${art('raster', '单色网点机械版画')}</div>
    <label class="terminal-search"><b aria-hidden="true">⌕</b><input id="lookup" type="search" maxlength="120" autocomplete="off" placeholder="键入材料、客户或订单号" value="${e(query)}"><span>索引</span></label>
    <div class="type-shortcuts">${['', '凭证', '耐磨', '会议'].map((q) => pick('query', q, q || '全部', query)).join('')}</div>
    <div class="type-results"><h2 aria-live="polite">${found.length} 项匹配</h2>${found.map((t) => `<a href="${target('tasks', t.id)}"><code>${e(t.orderId)}</code><b>${e(t.title)}</b><span>${statuses[t.status]} ↗</span></a>`).join('') || empty('没有匹配项，可缩短词片或选择全部。')}</div></div>`;
}
function ridge(s, p) {
  const dates = [...new Set(s.tasks.map((t) => t.deadline))].sort(),
    n = at(
      p.due ??
        Math.max(
          0,
          dates.findIndex((d) => d >= localDate())
        ),
      dates
    ),
    date = dates[n];
  const tasks = s.tasks.filter((t) => t.deadline === date);
  return `<div class="wind-station">${art('ridge', '山脊上展开的红色野外风标')}<div class="wind-shade"></div>${caption('办理时限 / FIELD SIGNAL', '时限风标')}
    <div class="wind-console"><div class="wind-date"><span>事项截止日期</span><b>${e(date?.slice(5).replace('-', '/') || '—')}</b></div>
    <div class="wind-controls">${dates.length ? `<label>期限刻度<input aria-label="期限刻度" type="range" min="0" max="${dates.length - 1}" value="${n}" data-range="due"></label><div>${dates.map((d, i) => pick('due', i, e(d.slice(5)), n)).join('')}</div>` : ''}</div>
    <div class="wind-list">${tasks.map((t) => `<a href="${target('tasks', t.id)}"><span>${statuses[t.status]}</span><b>${e(t.title)} ↗</b></a>`).join('')}</div></div></div>`;
}
function relay(s, p, role) {
  const oi = at(p.signalOrder, s.orders),
    order = s.orders[oi],
    line = p.channel === 'research' ? 'research' : 'finance';
  const tasks = s.tasks.filter((t) => t.orderId === order.id && t.line === line);
  const issues = s.tasks
    .filter((t) => t.orderId === order.id)
    .flatMap((t) => t.issues.map((item) => ({ t, item })));
  const messages = issues.filter(({ item }) => p.messages === 'all' || !item.closed);
  return `<div class="relay-room"><div>${caption('订单协作 / RELAY FIELD', '协办星图')}${select(
    'signalOrder',
    '协办订单',
    s.orders.map((o, i) => [i, o.customer]),
    oi
  )}</div>
    <div class="network"><i class="beam beam-west"></i><i class="beam beam-east"></i><div class="network-core"><span>订单</span>${e(order.id)}</div>
    ${pick('channel', 'research', '科研', line, 'node west')}${pick('channel', 'finance', '财务', line, 'node east')}</div>
    <div class="signal-feed"><div><h2>${line === 'finance' ? '财务节点' : '科研节点'}</h2>${tasks.map((t) => `<a href="${target('tasks', t.id)}">${e(t.title)} ↗</a>`).join('') || empty('此订单在该节点暂无任务。')}</div>
    <div><div class="signal-heading"><h2>补件会话</h2>${pick('messages', p.messages === 'all' ? 'open' : 'all', p.messages === 'all' ? '只看待办' : '含已关闭', null)}</div>${
      messages
        .map(
          ({ t, item }) => `<article><b>${e(item.question)}</b><p>${e(item.reply || '待科研回复')}</p>
     ${!item.closed && !item.reply && role === 'research' ? action('reply', t.id, '回复补件', item.id) : !item.closed && item.reply && editable(t, role) ? action('close-issue', t.id, '确认关闭', item.id) : taskLink(t)}</article>`
        )
        .join('') || empty('当前范围没有补件问题。')
    }</div></div></div>`;
}
function optic(s, p) {
  const fees = s.tasks
    .filter((t) => t.line === 'finance')
    .flatMap((t) => t.draft.fees.map((f) => ({ f, t })));
  if (!fees.length) return empty('费用明细录入后可在此核验凭证。');
  const n = at(p.focus, fees),
    { f, t } = fees[n];
  return `<div class="optical"><div class="optic-top">${caption('经费核验 / OPTICAL SCAN', '凭证显影室')}<span>${serial(n + 1)} / ${serial(fees.length)}</span></div>
    <div class="lens-stage" data-swipe="focus" data-index="${n}" data-count="${fees.length}">${art('optic', '金属校准盘的光学纹理')}
    <div class="reticle" style="--fx:${25 + (50 * n) / Math.max(1, fees.length - 1)}%"><i></i></div>
    <div class="scan-strip"><small>${e(f.voucher)}　/　${e(f.period)}</small><strong>${yen(f.amount)}</strong></div></div>
    <div class="scan-desk"><div><span>${e(f.projectId)}　/　${e(f.category)}</span>${go('查看凭证所属底稿', 'tasks', t.id)}</div>
    <label class="focus-wheel">调焦选凭证<input aria-label="调焦选凭证" data-range="focus" type="range" min="0" max="${fees.length - 1}" value="${n}"></label>
    ${steps('focus', n, fees.length, '上一张凭证', '下一张凭证')}</div></div>`;
}
function court(s, p) {
  const rooms = [
    ['委托室', '客户与订单', 'orders', s.orders.length, '份委托'],
    ['研究室', '研发项目', 'projects', s.orders.flatMap((o) => projectsFor(s, o.id)).length, '个已批项目'],
    ['交付室', '交付归档', 'archive', s.tasks.filter((t) => t.status === 'archived').length, '件归档成果']
  ];
  const n = at(p.room, rooms),
    r = rooms[n];
  return `<div class="courtyard room-${n}">${art('court', '科研服务院落的连廊与天窗')}<div class="court-shade"></div>
    ${caption('空间导办 / SERVICE COURT', '政务回廊')}
    <div class="doorway" data-swipe="room" data-index="${n}" data-count="3">${rooms.map((x, i) => pick('room', i, `<i></i><span>${x[0]}</span>`, n, 'door door-' + i)).join('')}</div>
    <div class="arrival"><div><span>${r[3]} ${r[4]}</span><h2>${r[0]}</h2></div>${go('进入' + r[1], r[2])}</div></div>`;
}
const views = { specimen, queue, arc, press, leaves, glyph, ridge, relay, optic, court };
export function workspace(ui, s, p, role, related = '') {
  const c = concepts[ui];
  return `<section class="scene scene-${ui}">${views[ui](s, p, role)}</section><footer class="colophon"><span>政务试办　·　虚构数据</span>${source(c)}${related}<a href="#designs">切换设计 ↗</a></footer>`;
}
export function recordHead(ui) {
  const c = concepts[ui];
  return `<div class="record-band"><a href="#dashboard">← ${c.name}</a><span>政务试办 / 业务记录</span></div>`;
}
