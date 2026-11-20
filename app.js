import {
  roles, statuses, lines, categories, initialState, actionsFor, actionLabels,
  newTask, projectsFor, snapshotProjects, editable, transition, log, localDate,
} from './model.js';
import { designs, gallery, visual } from './visuals.js';

const main = document.querySelector('main');
const dialog = document.querySelector('dialog');
const selectRole = document.querySelector('#role');
const notice = document.querySelector('#notice');
const storageKey = 'research-finance-demo-v1';
const finished = ['complete', 'archived'];
const checking = ['lead', 'reviewer', 'director'];
const navigation = {
  dashboard: ['工作台', '▦'], tasks: ['任务中心', '☷'], orders: ['客户与订单', '▤'],
  projects: ['研发项目', '◇'], archive: ['交付归档', '▣'],
};
let ui, currentVersion = null, spot = 0;
const appearance = document.querySelector('#appearance');
function syncAppearance() {
  const requested = new URL(location.href).searchParams.get('ui');
  ui = Object.hasOwn(designs, requested) ? requested : 'transit';
  document.documentElement.dataset.ui = ui;
  appearance.value = ui;
}
function scene(task = null, index = null) {
  return visual(ui, { state, role, task, index, spot, esc, money: yuan, actions: actionsFor });
}

let state = initialState();
let role = 'dispatcher';
let storageUnavailable = false;
try {
  const saved = localStorage.getItem(storageKey);
  if (saved) {
    const parsed = JSON.parse(saved);
    if (Array.isArray(parsed.orders) && Array.isArray(parsed.tasks)) {
      state = parsed;
      for (const task of state.tasks.filter(t => t.line === 'finance')) {
        for (const version of task.versions) {
          if (!version.projects?.length) version.projects = structuredClone(projectsFor(state, task.orderId));
        }
      }
    }
  }
} catch {
  storageUnavailable = true;
}
let toastTimer;
let filter = 'all';

function toast(message) {
  clearTimeout(toastTimer);
  notice.textContent = message;
  toastTimer = setTimeout(() => { notice.textContent = ''; }, 4400);
}

function commit(change) {
  const next = structuredClone(state);
  change(next);
  try {
    localStorage.setItem(storageKey, JSON.stringify(next));
  } catch {
    throw new Error('浏览器无法保存进度。请启用站点存储或释放浏览器空间后重试。');
  }
  state = next;
  render();
}

const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[char]);
const options = (items, selected) => items.map(([value, label]) =>
  `<option value="${esc(value)}" ${value === selected ? 'selected' : ''}>${esc(label)}</option>`).join('');
const link = (page, id) => `#${page}${id ? `/${encodeURIComponent(id)}` : ''}`;
const button = (text, command, details = '', kind = '') =>
  `<button type="button" class="button ${kind}" data-command="${command}" ${details}>${text}</button>`;
const tag = (text, kind) => `<span class="tag ${kind}">${text}</span>`;
const statusTag = task => tag(statuses[task.status], task.status);
const yuan = cents => new Intl.NumberFormat('zh-CN', {
  style: 'currency', currency: 'CNY',
}).format(cents / 100);
const findOrder = (task, data = state) => data.orders.find(order => order.id === task.orderId);
const findTask = (id, data = state) => data.tasks.find(task => task.id === id);
const dateFormatter = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' });
const attrs = id => `data-id="${esc(id)}"`;

function route() {
  const [page = '', ...parts] = location.hash.slice(1).split('/');
  try {
    return { page: page === 'designs' || Object.hasOwn(navigation, page) ? page : 'dashboard', id: decodeURIComponent(parts.join('/')) };
  } catch {
    return { page: 'dashboard', id: '' };
  }
}

function heading(title, subtitle, action = '') {
  return `<div class="page-head"><div><h1>${title}</h1><p class="sub">${subtitle}</p></div>${action}</div>`;
}

function panel(title, body, extra = '') {
  return `<section class="panel"><div class="panel-head"><h2>${title}</h2>${extra}</div>${body}</section>`;
}

function table(headers, rows, empty, kind = '') {
  if (!rows.length) return `<p class="empty">${empty}</p>`;
  return `<div class="table-wrap ${kind}" role="region" aria-label="明细表" tabindex="0"><table>
    <thead><tr>${headers.map(header => `<th scope="col">${header}</th>`).join('')}</tr></thead>
    <tbody>${rows.join('')}</tbody></table></div>`;
}

function isUrgent(task) {
  return !finished.includes(task.status) && task.deadline <= localDate(3);
}

function taskTable(tasks) {
  return table(['任务 / 客户', '状态', '截止日期', ''], tasks.map(task => {
    const detail = link('tasks', task.id);
    return `<tr><td><a class="row-title" href="${detail}">${esc(task.title)}</a>
      <span class="row-meta">${esc(findOrder(task).customer)} · ${esc(findOrder(task).id)}</span></td>
      <td>${statusTag(task)}</td><td class="${isUrgent(task) ? 'late' : ''}">${esc(task.deadline)}</td>
      <td><a class="text-link" aria-label="查看${esc(task.title)}" href="${detail}">查看 →</a></td></tr>`;
  }), '这个筛选条件下没有任务。', 'task-table');
}

const newOrderButton = () => role === 'dispatcher' ? button('＋ 新建订单', 'order', '', 'primary') : '';

function dashboard() {
  const today = new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' });
  const pending = state.tasks.filter(task => actionsFor(task, role, state).length);
  const example = state.tasks.find(task => task.line === 'finance' && findOrder(task).code === 'DEMO-001');
  const metrics = [
    ['我的待办', pending.length, '#tasks/mine'], ['待审核', state.tasks.filter(task => checking.includes(task.status)).length, '#tasks/checking'],
    ['临期与超期', state.tasks.filter(isUrgent).length, '#tasks/urgent'],
    ['已归档', state.tasks.filter(task => task.status === 'archived').length, '#archive'],
  ];
  const queue = pending.length ? `<ul class="queue">${pending.map(task => `<li><a href="${link('tasks', task.id)}">
    <div class="split"><strong>${esc(task.title)}</strong>${statusTag(task)}</div>
    <p>${esc(findOrder(task).customer)}</p></a></li>`).join('')}</ul>`
    : '<p class="empty">当前角色没有待办。可切换角色继续处理其他节点。</p>';

  return heading('研发服务工作台', `${today} · 当前为${roles[role]}视角`, newOrderButton()) + `
    ${scene()}
    <div class="stats">${metrics.map(([label, number, href]) =>
      `<a class="stat" href="${href}"><span class="metric-label">${label}</span><strong class="metric">${number}</strong></a>`).join('')}</div>
    <div class="content-grid">
      ${panel('近期任务', taskTable(state.tasks.slice(0, 6)), '<a class="text-link" href="#tasks">全部任务 →</a>')}
      <aside class="stack">
        ${panel('我的待办', queue)}
        ${example ? panel('从示例订单开始', '<div class="panel-body"><p>先以财务承办人接件，查看科研线已确认的立项清单。提交后切换到下一位审核人。</p></div>',
          `<a class="text-link" href="${link('tasks', example.id)}">打开示例 →</a>`) : ''}
      </aside>
    </div>`;
}

const filters = {
  all: '全部任务', mine: '我的待办', urgent: '临期与超期', checking: '待审核',
  research: '科研立项', finance: '费用归集',
};

function tasksPage(initialFilter) {
  if (Object.hasOwn(filters, initialFilter)) filter = initialFilter;
  const tasks = state.tasks.filter(task => {
    if (filter === 'mine') return actionsFor(task, role, state).length;
    if (filter === 'urgent') return isUrgent(task);
    if (filter === 'checking') return checking.includes(task.status);
    return filter === 'all' || task.line === filter;
  });
  return heading('任务中心', '按业务线和状态定位待办，查看提交版本与处理记录。') +
    panel('任务列表', taskTable(tasks),
      `<div class="toolbar"><label for="task-filter">筛选</label><select id="task-filter">${options(Object.entries(filters), filter)}</select></div>`);
}

function ordersPage(id) {
  const order = state.orders.find(item => item.id === id);
  if (!order) {
    return heading('客户与订单', '每份服务订单都关联一个客户和合同，科研与财务任务在订单下协作。', newOrderButton()) +
      panel('服务订单', table(['订单', '客户 / 客户编号', '合同编号', '任务归档', '截止日期'], state.orders.map(item => {
        const tasks = state.tasks.filter(task => task.orderId === item.id);
        return `<tr><td><a class="row-title" href="${link('orders', item.id)}">${esc(item.title)}</a>
          <span class="row-meta">${esc(item.id)}</span></td><td>${esc(item.customer)}<span class="row-meta">${esc(item.code)}</span></td>
          <td>${esc(item.contract)}</td><td>${tasks.filter(task => task.status === 'archived').length} / ${tasks.length}</td><td>${esc(item.deadline)}</td></tr>`;
      }), '暂无订单。'));
  }
  const tasks = state.tasks.filter(task => task.orderId === order.id);
  const canAssign = role === 'dispatcher';
  return heading(esc(order.title), `${esc(order.customer)} · ${esc(order.id)}`, canAssign ? button('＋ 派发任务', 'assign', attrs(order.id), 'primary') : '') +
    `<div class="stack">
      ${panel('订单信息', `<div class="panel-body"><p>客户编号 ${esc(order.code)}　·　合同编号 ${esc(order.contract)}</p>
        <p>服务年度 ${esc(order.year)}　·　截止日期 ${esc(order.deadline)}</p></div>`, '<a class="text-link" href="#orders">返回订单</a>')}
      ${panel('科研与财务任务', tasks.length ? taskTable(tasks) : '<p class="empty">订单已建档。以派单经理身份添加科研立项或费用归集任务。</p>')}
    </div>`;
}

function projectTable(projects, task, controls = false) {
  return table(['项目编号 / 名称', '负责人', '研发周期', '<span class="numeric">预算</span>', ...(controls ? [''] : [])],
    projects.map(project => `<tr><td><strong>${esc(project.name)}</strong><span class="row-meta">${esc(project.id)}</span></td>
    <td>${esc(project.person)}</td><td>${esc(project.start)} 至 ${esc(project.end)}</td><td class="numeric">${yuan(project.budget)}</td>
    ${controls ? `<td><div class="actions">
      ${button('编辑', 'project', `${attrs(task.id)} data-row="${esc(project.id)}"`, 'small')}
      ${button('移除', 'remove', `${attrs(task.id)} data-row="${esc(project.id)}"`, 'small danger')}</div></td>` : ''}</tr>`),
    '暂无项目。');
}

function projectsPage() {
  const rows = state.orders.flatMap(order => projectsFor(state, order.id).map(project =>
    `<tr><td><strong>${esc(project.name)}</strong><span class="row-meta">${esc(project.id)}</span></td>
    <td><a class="text-link" href="${link('orders', order.id)}">${esc(order.customer)}</a></td>
    <td>${esc(project.person)}</td><td>${esc(project.start)} 至 ${esc(project.end)}</td><td class="numeric">${yuan(project.budget)}</td></tr>`));
  return heading('研发项目', '科研立项通过内部末级审核后，项目即同步至同一订单的财务任务。') +
    panel('内部审核通过的立项清单', table(['项目编号 / 名称', '客户', '负责人', '研发周期', '预算'], rows, '暂无内部审核通过的研发项目。'));
}

function feeTable(task, fees, projects, controls) {
  const rows = fees.map(item => `<tr><td>${esc(projects.find(project => project.id === item.projectId)?.name || item.projectId)}
    <span class="row-meta">${esc(item.projectId)}</span></td><td>${esc(item.category)}</td><td>${esc(item.period)}</td>
    <td>${esc(item.voucher)}</td><td class="numeric">${yuan(item.amount)}</td>
    ${controls ? `<td><div class="actions">${button('编辑', 'fee', `${attrs(task.id)} data-row="${esc(item.id)}"`, 'small')}
      ${button('移除', 'remove', `${attrs(task.id)} data-row="${esc(item.id)}"`, 'small danger')}</div></td>` : ''}</tr>`);
  const total = yuan(fees.reduce((sum, item) => sum + item.amount, 0));
  return `${table(['研发项目', '费用类别', '期间', '凭证索引', '金额', ...(controls ? [''] : [])], rows, '暂无费用明细。')}
    <div class="panel-body"><div class="split"><span>明细合计</span><strong>${total}</strong></div>
      ${projects.length ? `<p class="sub">${projects.map(project => {
        const rows = fees.filter(item => item.projectId === project.id);
        return `${esc(project.id)} · ${rows.length ? yuan(rows.reduce((sum, item) => sum + item.amount, 0)) : '本底稿无明细'}`;
      }).join('　')}</p>` : ''}
    </div>`;
}

function issuesPanel(task) {
  const add = editable(task, role) ? button('＋ 发起补件', 'issue', attrs(task.id), 'small') : '';
  const list = task.issues.length ? `<ul class="issues">${task.issues.map(issue => `<li>
    <div class="split"><strong>${esc(issue.question)}</strong>${tag(issue.closed ? '已关闭' : (issue.reply ? '待财务确认' : '待科研补充'), issue.closed ? 'complete' : 'customer')}</div>
    ${issue.reply ? `<p class="sub preline">科研回复　${esc(issue.reply)}</p>` : ''}
    <div class="actions">
      ${!issue.closed && !issue.reply && role === 'research' ? button('回复补件', 'reply', `${attrs(task.id)} data-row="${esc(issue.id)}"`, 'small') : ''}
      ${!issue.closed && issue.reply && editable(task, role) ? button('确认关闭', 'close-issue', `${attrs(task.id)} data-row="${esc(issue.id)}"`, 'small') : ''}
    </div>
  </li>`).join('')}</ul>` : '<p class="sub">财务可登记缺项，由科研回复后关闭。</p>';
  return panel('两线补件', `<div class="panel-body">${list}</div>`, add);
}

function taskPage(task, versionIndex) {
  const order = findOrder(task);
  const id = attrs(task.id);
  const canEdit = editable(task, role) && versionIndex === null;
  const actions = actionsFor(task, role, state);
  const research = task.line === 'research';
  const version = versionIndex === null ? task.draft : task.versions[versionIndex] || task.draft;
  const frozen = versionIndex !== null || !['assigned', 'working', 'revision'].includes(task.status);
  const basis = versionIndex === null && frozen ? task.versions.at(-1) || version : version;
  const projects = research ? [] : frozen ? snapshotProjects(state, task, basis) : projectsFor(state, order.id);
  const phaseOrder = ['assigned', task.status === 'revision' ? 'revision' : 'working',
    'lead', 'reviewer', ...(task.high ? ['director'] : []), 'customer', 'complete', 'archived'];
  const path = phaseOrder.map(phase => `<li ${phase === task.status ? 'class="current" aria-current="step"' : ''}>${statuses[phase]}</li>`).join('');
  const versionControl = task.versions.length ? `<div class="toolbar"><label for="versions">版本</label>
    <select id="versions">${options([['current', '当前成果'], ...task.versions.map((_, index) => [String(index), `提交版 V${index + 1}`]).reverse()],
      versionIndex === null ? 'current' : String(versionIndex))}</select></div>` : '';
  const locked = versionIndex === null && finished.includes(task.status);
  const actionButtons = versionIndex === null ? actions.map(action =>
    button(actionLabels[action], action, id, ['return', 'revise'].includes(action) ? '' : 'primary')).join('') : '';

  return heading(esc(task.title), `<a class="text-link" href="${link('orders', order.id)}">${esc(order.customer)} · ${esc(order.id)}</a>
   　·　截止 ${esc(task.deadline)}　${statusTag(task)}`, `<div class="actions">${actionButtons}</div>`) +
  `${scene(task, versionIndex)}<ol class="milestones" aria-label="任务进度">${path}</ol>
    <div class="content-grid">
      <div class="stack">
        ${panel('作业底稿', `<div class="panel-body">
          ${!research && !projects.length ? '<p class="cue">等待科研立项通过内部审核。清单同步后即可登记费用。</p>' : ''}
          ${versionIndex === null && task.status === 'revision' ? '<p class="cue">修改后将生成新的提交版本，从主管审核重新开始。</p>' : ''}
          ${locked ? '<p class="cue">客户已确认，当前交付版本已锁定。</p>' : ''}
          <p><strong>作业说明</strong></p><p class="preline">${esc(version.summary || '待填写')}</p>
          <p><strong>材料索引</strong></p><p class="preline">${esc(version.evidence || '待填写')}</p>
          ${canEdit ? `<div class="actions">${button('编辑底稿', 'draft', id, 'small')}</div>` : ''}
        </div>`, versionControl)}
        ${research
          ? panel(task.relatedProject ? '关联研发项目' : '研发项目清单', projectTable(version.projects, task, canEdit && !task.relatedProject),
            canEdit && !task.relatedProject ? button('＋ 增加项目', 'project', id, 'small') : '')
          : panel('按项目归集费用', feeTable(task, version.fees, projects, canEdit && projects.length),
            canEdit && projects.length ? button('＋ 登记费用', 'fee', id, 'small') : '')}
        ${!research ? issuesPanel(task) : ''}
      </div>
      <aside class="stack">
        ${panel('处理记录', `<div class="panel-body"><ol class="timeline">${[...task.history].reverse().map(event => `<li>
          <strong>${esc(event.label)}${event.version ? ` · V${event.version}` : ''}</strong>
          <p>${roles[event.role]} · ${dateFormatter.format(new Date(event.at))}</p>
          ${event.note ? `<p class="preline">${esc(event.note)}</p>` : ''}</li>`).join('')}</ol></div>`)}
        ${task.status === 'archived' ? panel('归档成果', `<div class="panel-body"><p>归档文件包含提交版本、审核记录、两线补件与客户确认凭据。</p>
          <div class="actions">${button('下载归档', 'export', id, 'small')}</div></div>`) : ''}
      </aside>
    </div>`;
}

function archivePage() {
  const archived = state.tasks.filter(task => task.status === 'archived');
  return heading('交付归档', '查看锁定成果、各版底稿、审核意见与客户确认凭据。') + panel('归档清单',
    table(['归档成果 / 订单', '客户', '版本', ''], archived.map(task => {
      const order = findOrder(task);
      return `<tr><td><a class="row-title" href="${link('tasks', task.id)}">${esc(task.title)}</a><span class="row-meta">${esc(order.id)}</span></td>
        <td>${esc(order.customer)}</td><td>V${task.versions.length}</td><td>${button('下载归档', 'export', attrs(task.id), 'small')}</td></tr>`;
    }), '暂无归档成果。完成客户确认后，由派单经理执行归档。'));
}

function render(versionIndex = null) {
  currentVersion = versionIndex;
  syncAppearance();
  const { page, id } = route();
  main.dataset.page = page;
  document.querySelector('#breadcrumb').textContent = navigation[page]?.[0] || '界面展廊';
  document.querySelector('#navigation').innerHTML = '<p class="nav-label">业务导航</p>' +
    Object.entries(navigation).map(([key, [label, symbol]]) => `<a class="nav-link" href="${link(key)}"
      ${key === page ? 'aria-current="page"' : ''}><span class="nav-icon" aria-hidden="true">${symbol}</span>${label}</a>`).join('');
  const task = page === 'tasks' ? findTask(id) : null;
  const views = { dashboard, tasks: task ? () => taskPage(task, versionIndex) : () => tasksPage(id),
    orders: () => ordersPage(id), projects: projectsPage, archive: archivePage,
    designs: () => heading('界面展廊', '选择一套工作台开始体验。各方案共用本浏览器中的订单、底稿与办理进度。') + gallery(esc) };
  main.innerHTML = views[page]();
}

const input = (label, name, value = '', extra = '', type = 'text', full = false) =>
  `<label class="field ${full ? 'full' : ''}">${label}<input required type="${type}" name="${name}" value="${esc(value)}" ${extra}></label>`;
const textarea = (label, name, value = '', required = true) =>
  `<div class="field full"><label for="field-${name}">${label}</label><textarea id="field-${name}" name="${name}"
    maxlength="1000" ${required ? 'required' : ''}>${esc(value)}</textarea></div>`;
const dropdown = (label, name, list, selected) =>
  `<label class="field">${label}<select name="${name}">${options(list, selected)}</select></label>`;

function showDialog(title, fields, submit, callback, copy = '') {
  dialog.innerHTML = `<div class="dialog-head"><h2 id="dialog-title">${title}</h2>
    <button class="button icon-button" type="button" aria-label="关闭" data-close>×</button></div>
    <form class="dialog-content"><p class="sub">${copy}</p><div class="fields">${fields}</div>
    <p class="form-error" role="alert"></p>
    <div class="actions"><button type="button" class="button" data-close>取消</button><button type="submit" class="button primary">${submit}</button></div></form>`;
  for (const control of dialog.querySelectorAll('[data-close]')) control.onclick = () => dialog.close();
  dialog.querySelector('form').onsubmit = event => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const get = name => String(values.get(name) ?? '').trim();
    try {
      callback(get);
      dialog.close();
      main.focus();
      toast('已保存');
    } catch (error) {
      dialog.querySelector('.form-error').textContent = error.message;
    }
  };
  dialog.showModal();
}

function addOrder() {
  if (role !== 'dispatcher') return;
  const year = new Date().getFullYear();
  showDialog('新建服务订单', input('客户名称', 'customer', '', 'maxlength="80"') +
    input('客户编号', 'code', '', 'maxlength="30" placeholder="如 DEMO-004"') +
    input('合同编号', 'contract', '', 'maxlength="30"') +
    input('服务年度', 'year', year, 'min="2000" max="2100" step="1"', 'number') +
    input('截止日期', 'deadline', localDate(7), '', 'date') +
    input('订单名称', 'title', '', 'maxlength="80"', 'text', true), '创建订单', get => {
    const order = Object.fromEntries(['customer', 'code', 'contract', 'year', 'deadline', 'title'].map(key => [key, get(key)]));
    if (Object.values(order).some(value => !value)) throw new Error('请填写所有字段。');
    order.id = `DD-${order.year}-${String(state.orders.length + 1).padStart(3, '0')}`;
    const customer = state.orders.find(item => item.code.toUpperCase() === order.code.toUpperCase());
    if (customer && customer.customer !== order.customer) throw new Error('该客户编号已关联其他客户。');
    const contract = state.orders.find(item => item.contract.toUpperCase() === order.contract.toUpperCase());
    if (contract && contract.code.toUpperCase() !== order.code.toUpperCase()) throw new Error('该合同编号已关联其他客户。');
    commit(next => next.orders.unshift(order));
    location.hash = link('orders', order.id);
  }, '请使用虚构企业名称和编号。');
}

function assign(id) {
  if (role !== 'dispatcher') return;
  const order = state.orders.find(item => item.id === id);
  const projects = projectsFor(state, id);
  const kinds = [['research', '科研 · 新立项'], ['finance', '财务 · 费用归集'],
    ...projects.map(p => [`follow/${p.id}`, `科研 · 跟进项目 ${p.id}（${p.name}）`])];
  showDialog('派发任务', dropdown('业务线与事项', 'kind', kinds) +
    input('任务截止日期', 'deadline', order.deadline, `max="${esc(order.deadline)}"`, 'date') +
    input('任务名称', 'title', '', 'maxlength="80"', 'text', true) +
    '<label class="check full"><input type="checkbox" name="high">重大事项，由总监终审</label>', '派单', get => {
    const kind = get('kind');
    const task = newTask(order, kind === 'finance' ? 'finance' : 'research', get('deadline'), get('high') === 'on', get('title'));
    if (kind.startsWith('follow/')) {
      const project = projects.find(p => p.id === kind.slice(7));
      if (!project) throw new Error('请选择有效的研发项目。');
      task.relatedProject = project.id;
      task.draft.projects = [structuredClone(project)];
    }
    if (!task.title || task.deadline > order.deadline) throw new Error('请填写名称，且任务截止日期须在订单期限内。');
    log(task, role, '经理派单');
    commit(next => next.tasks.unshift(task));
    location.hash = link('tasks', task.id);
  }, '任务将进入对应承办人的待办。');
}

function draftDialog(task) {
  showDialog('编辑作业底稿', textarea('作业说明', 'summary', task.draft.summary) +
    textarea('材料索引', 'evidence', task.draft.evidence), '保存底稿', get => {
    const summary = get('summary');
    const evidence = get('evidence');
    if (!summary || !evidence) throw new Error('请填写作业说明和材料索引。');
    commit(next => Object.assign(findTask(task.id, next).draft, { summary, evidence }));
  }, '可登记虚构的材料名称和编号，便于审核时对照。');
}

function cents(value) {
  if (!/^\d{1,9}(?:\.\d{1,2})?$/.test(value)) throw new Error('请输入有效金额，最多两位小数。');
  const [units, fraction = ''] = value.split('.');
  return Number(units) * 100 + Number(fraction.padEnd(2, '0'));
}

function editRow(task, type, rowId) {
  const project = type === 'project';
  const key = project ? 'projects' : 'fees';
  const row = task.draft[key].find(item => item.id === rowId);
  const year = findOrder(task).year;
  const amountInput = (label, name, amount) => input(label, name,
    amount === undefined ? '' : (amount / 100).toFixed(2), 'step="0.01" min="0" max="999999999.99"', 'number');
  const fields = project
    ? input('项目编号', 'id', row?.id || '', row ? 'readonly' : 'maxlength="32" placeholder="如 RD-005"') +
      input('项目负责人', 'person', row?.person, 'maxlength="40"') +
      input('项目名称', 'name', row?.name, 'maxlength="80"', 'text', true) +
      input('开始日期', 'start', row?.start || `${year}-01-01`, '', 'date') +
      input('结束日期', 'end', row?.end || `${year}-12-31`, '', 'date') + amountInput('预算（元）', 'budget', row?.budget)
    : dropdown('研发项目', 'projectId', projectsFor(state, task.orderId).map(p => [p.id, `${p.id} · ${p.name}`]), row?.projectId) +
      dropdown('费用类别', 'category', categories.map(category => [category, category]), row?.category) +
      input('归集期间', 'period', row?.period || `${year}-01`, `min="${year}-01" max="${year}-12"`, 'month') +
      input('凭证索引 / 无费用说明', 'voucher', row?.voucher, 'maxlength="80"') + amountInput('金额（元）', 'amount', row?.amount);
  showDialog(project ? '研发项目' : '费用明细', fields, '保存', get => {
    let item;
    if (project) {
      item = { id: get('id').toUpperCase(), person: get('person'), name: get('name'), start: get('start'), end: get('end'), budget: cents(get('budget')) };
      if (!item.id || !item.person || !item.name || item.start > item.end) throw new Error('请完善项目资料并检查研发周期。');
      if (task.draft.projects.some(other => other.id === item.id && other.id !== rowId)) throw new Error('该项目编号已存在于本订单。');
      if (state.tasks.some(other => other.orderId === task.orderId && other.id !== task.id && other.line === 'research' &&
        !other.relatedProject && other.draft.projects.some(p => p.id === item.id))) throw new Error('本订单的其他立项任务已使用此编号。');
    } else {
      item = { id: rowId || crypto.randomUUID(), projectId: get('projectId'), category: get('category'), period: get('period'),
        voucher: get('voucher'), amount: cents(get('amount')) };
      if (!item.voucher || !new RegExp(`^${year}-(0[1-9]|1[0-2])$`).test(item.period) ||
        !projectsFor(state, task.orderId).some(p => p.id === item.projectId) || !categories.includes(item.category)) {
        throw new Error('请填写有效的项目、类别、服务年度内的期间和凭证索引。');
      }
    }
    commit(next => {
      const rows = findTask(task.id, next).draft[key];
      const index = rows.findIndex(old => old.id === rowId);
      if (index >= 0) rows[index] = item;
      else rows.push(item);
    });
  });
}

function issueDialog(task, command, rowId) {
  const labels = { issue: '发起补件', reply: '回复补件', 'close-issue': '确认关闭补件' };
  const field = command === 'close-issue' ? '' : textarea(command === 'issue' ? '需要补充的资料' : '补充说明或材料索引', 'note');
  showDialog(labels[command], field, labels[command], get => commit(next => {
    const current = findTask(task.id, next);
    const issue = current.issues.find(item => item.id === rowId);
    const note = get('note');
    if (command !== 'close-issue' && !note) throw new Error('请填写补件说明。');
    if (command === 'issue') current.issues.push({ id: crypto.randomUUID(), question: note, reply: '', closed: false });
    if (command === 'reply') issue.reply = note;
    if (command === 'close-issue') issue.closed = true;
    log(current, role, labels[command], note || issue?.question);
  }));
}

function exportTask(task) {
  if (task.status !== 'archived') return;
  const record = { demo: true, order: findOrder(task), task, projects: snapshotProjects(state, task, task.versions.at(-1)) };
  const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${task.id}-archive.json`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function actionDialog(task, action) {
  const label = actionLabels[action];
  let field = '';
  let copy = '';
  const noteLabels = { approve: '审核意见（选填）', return: '退回意见', confirm: '确认凭据或说明', revise: '客户修改意见' };
  if (noteLabels[action]) field = textarea(noteLabels[action], 'note', '', action !== 'approve');
  if (action === 'confirm') copy = '请模拟登记客户在邮件或其他渠道作出的确认。确认后交付版本锁定。';
  if (action === 'submit') copy = `本次提交将保存为 V${task.versions.length + 1} 并进入主管审核。`;
  if (action === 'archive') copy = '归档后可查看和下载成果。';
  showDialog(label, field, label, get => commit(next => transition(next, findTask(task.id, next), role, action, get('note'))), copy);
}

main.addEventListener('click', event => {
  const frame = event.target.closest('[data-frame]');
  if (frame) return render(Number(frame.dataset.frame));
  const cue = event.target.closest('[data-spot]');
  if (cue) {
    spot = Number(cue.dataset.spot);
    render(currentVersion);
    main.querySelector(`[data-spot="${spot}"]`)?.focus({ preventScroll: true });
    return;
  }
  const control = event.target.closest('[data-command]');
  if (!control) return;
  const { command, id, row } = control.dataset;
  if (command === 'order') return addOrder();
  if (command === 'assign') return assign(id);
  const task = findTask(id);
  if (!task) return;
  const canEdit = editable(task, role);
  if (command === 'export') return exportTask(task);
  if (actionsFor(task, role, state).includes(command)) return actionDialog(task, command);
  if (command === 'draft' && canEdit) return draftDialog(task);
  if (command === 'project' && canEdit && task.line === 'research') return editRow(task, command, row);
  if (command === 'fee' && canEdit && task.line === 'finance' && projectsFor(state, task.orderId).length) return editRow(task, command, row);
  if (command === 'remove' && canEdit) {
    return showDialog('移除草稿明细', '', '移除', () => commit(next => {
      const key = task.line === 'research' ? 'projects' : 'fees';
      const draft = findTask(id, next).draft;
      draft[key] = draft[key].filter(item => item.id !== row);
    }), '此操作将移除当前草稿中的该条明细。');
  }
  const issue = task.issues.find(item => item.id === row);
  if ((command === 'issue' && canEdit && task.line === 'finance') ||
    (command === 'reply' && role === 'research' && issue && !issue.closed && !issue.reply) ||
    (command === 'close-issue' && canEdit && issue?.reply && !issue.closed)) return issueDialog(task, command, row);
});

main.addEventListener('change', event => {
  if (event.target.id === 'task-filter') {
    filter = event.target.value;
    location.hash = link('tasks', filter === 'all' ? '' : filter);
  }
  if (event.target.id === 'versions') render(event.target.value === 'current' ? null : Number(event.target.value));
});

selectRole.innerHTML = options(Object.entries(roles), role);
appearance.innerHTML = options(Object.entries(designs).map(([key,[name]]) => [key,name]));
appearance.addEventListener('change', () => {
  const url = new URL(location.href);
  url.searchParams.set('ui', appearance.value);
  if (route().page === 'designs') url.hash = 'dashboard';
  history.replaceState(null, '', url);
  render(currentVersion);
});
selectRole.addEventListener('change', () => {
  role = selectRole.value;
  render();
  toast(`已切换为${roles[role]}`);
});

window.addEventListener('hashchange', () => {
  if (location.hash === '#main') return;
  filter = 'all';
  render();
  main.focus();
  window.scrollTo(0, 0);
});
document.querySelector('.skip').addEventListener('click', event => {
  event.preventDefault();
  main.focus();
});
render();
if (storageUnavailable) toast('浏览器存储不可用，当前展示初始演示数据。');
