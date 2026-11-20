import { internalVersion, projectsFor, roles, statuses } from './model.js';

export const designs = {
  transit: ['双线换乘图', '跟着两条业务线找到下一次交接。'],
  proof: ['朱墨校样', '用审阅批注对照两次提交的字段变化。'],
  optics: ['偏振光显微镜', '用项目编号生成独有的薄片纹理。'],
  departures: ['机场翻牌屏', '在翻牌行上读取期限、状态和下一位经办人。'],
  ledger: ['当代中式账簿', '翻阅客户分册，查看立项预算与任务进度。'],
  strata: ['地质剖面', '沿事件地层回看每一步办理记录。'],
  swiss: ['瑞士巨字海报', '用一个大数字突出当前角色的待办。'],
  film: ['电影剪辑台', '逐帧查看提交版本，对照相邻两版的变化。'],
  weave: ['提花织物', '逐行检查项目、材料和审核记录的齐备情况。'],
  stage: ['舞台追光', '让当前事项、材料与金额依次进入审阅中心。'],
};

const nextRole = task => ({
  assigned: task.line, working: task.line, revision: task.line, customer: 'dispatcher',
  complete: 'dispatcher', archived: null,
})[task.status] ?? (roles[task.status] ? task.status : null);

function projectHue(key) {
  let value = 0;
  for (const char of key) value = (value * 31 + char.codePointAt(0)) >>> 0;
  return (value * 137.508) % 360;
}

function versionFields(version, money) {
  const rows = new Map([['作业说明', version.summary], ['材料索引', version.evidence]]);
  for (const p of version.projects || []) rows.set(`项目 ${p.id}`, `${p.name} · ${p.person} · ${p.start} 至 ${p.end} · ${money(p.budget)}`);
  for (const f of version.fees || []) rows.set(`明细 ${f.id}`, `${f.period} · ${f.projectId} · ${f.category} · ${f.voucher} · ${money(f.amount)}`);
  return rows;
}

function compare(task, index, esc, money) {
  if (index < 1) return '';
  const before = versionFields(task.versions[index - 1], money);
  const after = versionFields(task.versions[index], money);
  const fields = [...new Set([...before.keys(), ...after.keys()])].filter(key => before.get(key) !== after.get(key));
  const rows = fields.map(key => `<tr><th>${esc(key)}</th><td>${esc(before.get(key) || '—')}</td><td>${esc(after.get(key) || '—')}</td></tr>`).join('');
  return `<details class="version-diff" open><summary>V${index} → V${index + 1} · ${fields.length} 项变化</summary>
    ${rows ? `<div class="table-wrap"><table><thead><tr><th>字段</th><th>上一版</th><th>本版</th></tr></thead><tbody>${rows}</tbody></table></div>` : ''}</details>`;
}

export function gallery(esc) {
  return `<div class="design-grid">${Object.entries(designs).map(([id, [name, note]]) =>
    `<a class="design-card" href="?ui=${id}#dashboard"><img loading="lazy" width="560" height="350" src="./previews/${id}.webp" alt="${esc(name)}工作台预览">
      <div><h2>${esc(name)}</h2><span aria-hidden="true">↗</span><p>${esc(note)}</p></div></a>`).join('')}</div>`;
}

export function visual(ui, { state, role, task, index, spot, esc, money, actions }) {
  const order = task && state.orders.find(o => o.id === task.orderId);
  const tasks = order ? state.tasks.filter(t => t.orderId === order.id) : state.tasks;
  const chosen = task || tasks.find(t => actions(t, role, state).length) || tasks[0];
  const taskUrl = t => `#tasks/${encodeURIComponent(t.id)}`;
  const orderUrl = o => `#orders/${encodeURIComponent(o.id)}`;
  const title = (heading, data = '') => `<header class="scene-head"><h2>${heading}</h2><span>${esc(data)}</span></header>`;
  const responsible = t => roles[nextRole(t)] || '已归档';
  const owner = t => state.orders.find(o => o.id === t.orderId);
  const events = tasks.flatMap(t => t.history.map((e, i) => ({ t, e, i })))
    .sort((a, b) => b.e.at.localeCompare(a.e.at) || b.i - a.i);
  const focusEvents = task ? events.filter(row => row.t.id === task.id) : events;
  const summary = chosen?.draft;
  const n = index ?? ((task?.versions.length || 0) - 1);
  const frames = task ? task.versions.map((v, i) => `<button type="button" data-frame="${i}" aria-pressed="${i === n}">
    <b>V${i + 1}</b><span>${esc(v.summary || '提交底稿')}</span></button>`) :
    tasks.filter(t => t.versions.length).slice(0, 5).map(t => `<a href="${taskUrl(t)}"><b>V${t.versions.length}</b><span>${esc(t.title)}</span></a>`);
  let content;
  switch (ui) {
    case 'transit': {
      const track = (line, name) => {
        const items = tasks.filter(t => t.line === line);
        const active = items.find(t => !['complete','archived'].includes(t.status)) || items[0];
        return `<div class="rail rail-${line}"><a class="route-code" href="#tasks/${line}">${name}</a>
          <a class="station" href="${active ? taskUrl(active) : '#orders'}"><i></i>${active ? esc(active.title) : '待派单'}</a>
          <a class="station" href="${active ? taskUrl(active) : '#orders'}"><i></i>${active ? statuses[active.status] : '待接件'}</a></div>`;
      };
      content = title('科研与财务换乘图', order?.id || '业务线路') + `<div class="map-grid"><div>${track('research','科研线')}${track('finance','财务线')}</div>
        <a class="exchange" href="${order ? orderUrl(order) : '#orders'}"><i>⇄</i>订单交接</a></div>`;
      break;
    }
    case 'proof': {
      const marked = focusEvents.find(({e}) => ['退回修改','登记客户修改意见'].includes(e.label));
      content = title('审阅校样', task ? `底稿 V${Math.max(0,n + 1)}` : '审核工作台') + `<div class="proof-sheet"><div>
        <small>${esc(owner(marked?.t || chosen).id)}</small><h3>${esc((marked?.t || chosen).title)}</h3>
        <p>${esc((index !== null && task ? task.versions[n] : (marked?.t || chosen).draft).summary || '待填写作业说明')}</p></div>
        <aside><b>${marked ? '退回批注' : '审阅记录'}</b><p>${esc(marked?.e.note || statuses[chosen.status])}</p>
        <a href="${taskUrl(marked?.t || chosen)}">查看底稿 ↗</a></aside></div>` +
        (task ? compare(task, n, esc, money) : '');
      break;
    }
    case 'optics': {
      const samples = task?.line === 'research'
        ? (index === null ? task.draft : task.versions[index]).projects.map(p => ({o:order,p}))
        : (order ? [order] : state.orders).flatMap(o => projectsFor(state,o.id).map(p => ({ o,p }))).slice(0,5);
      content = title('项目薄片库', task?.line === 'research' ? '本版科研底稿' : '内部审核通过的项目') + `<div class="samples">${samples.map(({o,p}) => {
        const hue = projectHue(o.id + p.id);
        return `<a href="${orderUrl(o)}"><i class="specimen" style="--h:${Math.round(hue)};--angle:${Math.round(hue)}deg"></i>
          <span><small>${esc(p.id)}</small><b>${esc(p.name)}</b></span></a>`;
      }).join('') || '<p>立项通过内部审核后显示项目薄片。</p>'}</div>`;
      break;
    }
    case 'departures': {
      const board = (task ? [task, ...tasks.filter(t => t !== task)] : [...tasks].sort((a,b) => a.deadline.localeCompare(b.deadline))).slice(0,4);
      content = title('任务调度屏', '值班岗位 / 办理状态') + `<div class="flaps">${board.map(t => `<a href="${taskUrl(t)}">
        <time>${esc(t.deadline.slice(5))}</time><b>${esc(t.title)}</b><span>${responsible(t)}</span><em>${statuses[t.status]}</em></a>`).join('')}</div>`;
      break;
    }
    case 'ledger': {
      content = title('客户分册', '已立项预算 · 人民币') + `<div class="ledger-books">${(order ? [order] : state.orders.slice(0,3)).map(o =>
        `<a href="${orderUrl(o)}"><i aria-hidden="true"></i><small>${esc(o.id)}</small><h3>${esc(o.customer)}</h3>
        <b>${money(projectsFor(state,o.id).reduce((s,p) => s+p.budget,0))}</b><span>${state.tasks.filter(t => t.orderId === o.id).length} 项任务</span></a>`).join('')}</div>`;
      break;
    }
    case 'strata': {
      content = title('办理剖面', '最近记录在上') + `<div class="strata">${focusEvents.slice(0,4).map(({t,e}, i) =>
        `<a href="${taskUrl(t)}" style="--depth:${i}"><time>${esc(e.at.slice(0,10))}</time><b>${esc(e.label)}</b><span>${esc(t.title)} · ${roles[e.role]}</span></a>`).join('')}</div>`;
      break;
    }
    case 'swiss': {
      const due = (task ? [task] : tasks).filter(t => actions(t,role,state).length);
      content = `<div class="swiss-poster"><strong>${String(due.length).padStart(2,'0')}</strong><div><small>${roles[role]}</small>
        <h2>等你办理</h2><a href="${due.length ? taskUrl(due[0]) : '#tasks/mine'}">${due.length ? esc(due[0].title) : '我的待办'}　↗</a></div></div>`;
      break;
    }
    case 'film':
      content = title(task ? '底稿剪辑台' : '提交片库', task ? '选择一帧查看该版底稿' : '已提交成果') +
        `<div class="filmstrip">${frames.join('') || '<p>提交后生成第一帧。</p>'}</div>` + (task ? compare(task, n, esc, money) : '');
      break;
    case 'weave': {
      const rows = (task ? [task,...tasks.filter(t => t !== task)] : tasks).slice(0,4);
      content = title('订单资料织样', '◆ 已具备　◇ 待补齐') + `<div class="weave-wrap"><table class="weave-matrix"><thead><tr><th>任务</th>${['材料索引','项目关联','提交底稿','内审通过','客户确认'].map(x => `<th>${x}</th>`).join('')}</tr></thead>
        <tbody>${rows.map(t => `<tr><th><a href="${taskUrl(t)}">${esc(t.title)}</a></th>${[t.draft.evidence.trim(),t.line === 'research' ? t.draft.projects.length : projectsFor(state,t.orderId).length,t.versions.length,internalVersion(t),['complete','archived'].includes(t.status)].map(v =>
          `<td class="${v ? 'thread' : 'hole'}" aria-label="${v ? '已具备' : '待补齐'}">${v ? '◆' : '◇'}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
      break;
    }
    case 'stage': {
      const v = index !== null && task ? task.versions[n] : summary;
      const amount = chosen.line === 'research' ? v.projects.reduce((s,p) => s+p.budget,0) : v.fees.reduce((s,f) => s+f.amount,0);
      const sections = [['当前事项',chosen.title], ['材料索引',v.evidence || '待填写'], [chosen.line === 'research' ? '项目预算' : '归集金额',money(amount)]];
      content = title('审阅舞台', order?.id || owner(chosen).id) + `<div class="stage-floor"><div class="light-cues">${sections.map(([label],i) =>
        `<button type="button" data-spot="${i}" aria-pressed="${spot === i}">${label}</button>`).join('')}</div>
        <div class="lit-object"><small>${sections[spot][0]}</small><h3>${esc(sections[spot][1])}</h3><a href="${taskUrl(chosen)}">查看任务 ↗</a></div></div>`;
      break;
    }
  }
  return `<section class="scene scene-${ui}" aria-label="${designs[ui][0]}">${content}</section>`;
}
