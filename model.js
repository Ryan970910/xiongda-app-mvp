export const roles = {
  dispatcher: '派单经理',
  research: '科研承办人',
  finance: '财务承办人',
  lead: '业务主管',
  reviewer: '复审经理',
  director: '总监',
};

export const statuses = {
  assigned: '待接件', working: '办理中', revision: '修改中', lead: '待主管审核',
  reviewer: '待经理复审', director: '待总监终审', customer: '待客户确认',
  complete: '已完成', archived: '已归档',
};

export const lines = { research: '科研立项', finance: '费用归集' };
export const categories = ['人员人工', '直接投入', '折旧', '无形资产摊销', '设计及试验等费用', '其他相关费用'];

export function localDate(offset = 0) {
  const date = new Date();
  date.setDate(date.getDate() + offset);
  return [date.getFullYear(), date.getMonth() + 1, date.getDate()]
    .map(x => String(x).padStart(2, '0')).join('-');
}

export function newTask(order, line, deadline, high = false, title = lines[line]) {
  return {
    id: `${order.id}-${line}-${crypto.randomUUID()}`, orderId: order.id, title, line, deadline, high,
    status: 'assigned', draft: { summary: '', evidence: '', projects: [], fees: [] },
    history: [], versions: [], issues: [],
  };
}

export function internalVersion(task) {
  const approval = task.history.findLast(event => event.label === actionLabels.approve &&
    event.role === (task.high ? 'director' : 'reviewer'));
  return approval?.version || 0;
}

export function projectsFor(state, orderId, exceptId) {
  return state.tasks.filter(task => task.orderId === orderId && task.line === 'research' &&
    task.id !== exceptId && !task.relatedProject).flatMap(task =>
    task.versions[internalVersion(task) - 1]?.projects || []);
}

export function snapshotProjects(state, task, version) {
  if (task.line === 'research') return version.projects;
  return version.projects?.length ? version.projects : projectsFor(state, task.orderId);
}

export function editable(task, role) {
  return task.line === role && ['working', 'revision'].includes(task.status);
}

export function actionsFor(task, role, state) {
  if (task.status === 'assigned' && task.line === role) return ['accept'];
  if (editable(task, role)) {
    return task.line === 'research' || projectsFor(state, task.orderId).length ? ['submit'] : [];
  }
  if (['lead', 'reviewer', 'director'].includes(task.status) && task.status === role) return ['approve', 'return'];
  if (task.status === 'customer' && role === 'dispatcher') return ['confirm', 'revise'];
  if (task.status === 'complete' && role === 'dispatcher') return ['archive'];
  return [];
}

export const actionLabels = {
  accept: '确认接件', submit: '提交审核', approve: '审核通过', return: '退回修改',
  confirm: '登记客户确认', revise: '登记客户修改意见', archive: '归档',
};

export function log(task, role, label, note = '', at = new Date().toISOString()) {
  task.history.push({ role, label, note, at, version: task.versions.length });
}

export function transition(state, task, role, action, note = '') {
  if (!actionsFor(task, role, state).includes(action)) throw new Error('当前角色或任务状态无法执行此操作。');
  const details = note.trim();
  if (['return', 'confirm', 'revise'].includes(action) && !details) throw new Error('请填写意见或客户确认凭据。');
  const { draft } = task;
  if (action === 'submit') {
    if (!draft.summary.trim() || !draft.evidence.trim()) throw new Error('请先保存作业说明和材料索引。');
    if (task.line === 'research' && !task.relatedProject && !draft.projects.length) throw new Error('请至少录入一个研发项目。');
    if (task.line === 'finance') {
      const projects = projectsFor(state, task.orderId);
      if (draft.fees.some(row => !projects.some(project => project.id === row.projectId))) throw new Error('有明细引用的项目已调整，请重新选择项目。');
      if (task.issues.some(issue => !issue.closed)) throw new Error('请先关闭所有补件问题。');
    }
    task.versions.push(structuredClone(draft));
    if (task.line === 'finance') task.versions.at(-1).projects = structuredClone(projectsFor(state, task.orderId));
  }
  if (action === 'approve' && task.line === 'research' && !task.relatedProject &&
      role === (task.high ? 'director' : 'reviewer')) {
    const elsewhere = projectsFor(state, task.orderId, task.id);
    if (draft.projects.some(p => elsewhere.some(other => other.id === p.id))) throw new Error('同一订单中有重复的立项编号，请退回修改。');
    const previous = task.versions[internalVersion(task) - 1]?.projects || [];
    const removed = previous.filter(p => !draft.projects.some(current => current.id === p.id));
    const used = state.tasks.filter(other => other.orderId === task.orderId && other.id !== task.id);
    if (removed.some(p => used.some(other => other.relatedProject === p.id || other.draft.fees.some(f => f.projectId === p.id)))) {
      throw new Error('拟移除的项目已由同单其他任务引用，请退回核对。');
    }
  }
  const next = {
    accept: 'working', submit: 'lead', return: 'revision', confirm: 'complete',
    revise: 'revision', archive: 'archived',
  };
  task.status = action === 'approve'
    ? ({ lead: 'reviewer', reviewer: task.high ? 'director' : 'customer', director: 'customer' })[task.status]
    : next[action];
  log(task, role, actionLabels[action], details);
}

export function initialState() {
  const year = new Date().getFullYear();
  const orders = [
    { id: `DD-${year}-001`, customer: '澄屿精密制造（示例）', code: 'DEMO-001', contract: `HT-${year}-001`, title: '年度研发资料与费用整理', year, deadline: localDate(6) },
    { id: `DD-${year}-002`, customer: '霁云新材料（示例）', code: 'DEMO-002', contract: `HT-${year}-002`, title: '新材料研发项目立项', year, deadline: localDate(12) },
    { id: `DD-${year}-003`, customer: '远岑装备科技（示例）', code: 'DEMO-003', contract: `HT-${year}-003`, title: '工装改进项目资料归档', year, deadline: localDate(-5) },
  ];
  const [first, second, third] = orders;
  const tasks = [newTask(first, 'finance', localDate(2)), newTask(second, 'research', localDate(9), true),
    newTask(first, 'research', localDate(4)), newTask(third, 'research', localDate(-5))];
  const [finance, nextResearch, research, archived] = tasks;
  const project = (id, name, budget, person) => ({ id, name, budget, person, start: `${year}-01-01`, end: `${year}-12-31` });
  const firstProjects = [project('RD-001', '精密伺服控制系统研发', 32000000, '陈岑'), project('RD-002', '轻量化定位夹具研发', 18000000, '林榆')];
  const archivedProjects = [project('RD-003', '智能检测工装改进', 9600000, '程言')];
  const stagedProjects = [project('RD-004', '低温耐磨复合涂层研究', 22000000, '梁澈')];
  const sampleTime = `${localDate(-3)}T09:30:00+08:00`;
  for (const task of tasks) {
    task.id = `${task.orderId}-${task.line}`;
    log(task, 'dispatcher', '经理派单', '', sampleTime);
  }
  for (const [task, projects, completed] of [[research, firstProjects, true], [archived, archivedProjects, true], [nextResearch, stagedProjects, false]]) {
    task.draft = { summary: '已整理项目目标、周期、预算和人员安排，待按立项清单复核。', evidence: '会议纪要（示例）；项目任务书（示例）', projects, fees: [] };
    transition({ tasks }, task, 'research', 'accept');
    if (task === nextResearch) {
      task.title = '耐磨涂层立项复审';
      task.draft.projects[0].budget = 20000000;
      task.draft.summary = '耐磨涂层研发预算 20 万元，申请立项。';
      transition({ tasks }, task, 'research', 'submit');
      transition({ tasks }, task, 'lead', 'return', '预算缺少低温耐磨试验的 2 万元检测费，请核对项目预算与试验方案。');
      task.draft.projects[0].budget = 22000000;
      task.draft.summary = '研发预算调整为 22 万元，已补入低温耐磨试验的检测费用。';
      task.draft.evidence = '立项会议纪要（示例）；低温试验方案与检测报价（示例）';
    }
    transition({ tasks }, task, 'research', 'submit');
    transition({ tasks }, task, 'lead', 'approve');
    if (completed) {
      transition({ tasks }, task, 'reviewer', 'approve');
      transition({ tasks }, task, 'dispatcher', 'confirm', '示例：客户通过邮件确认本版立项清单。');
    }
  }
  transition({ tasks }, archived, 'dispatcher', 'archive');
  finance.draft = {
    summary: '按已确认的两个研发项目登记期间费用与凭证索引，供财务复核。',
    evidence: '费用发生明细（示例）；项目材料凭证（示例）', projects: [],
    fees: [
      { id: 'F1', projectId: 'RD-001', category: categories[0], period: `${year}-03`, voucher: '凭 0301', amount: 3850000 },
      { id: 'F2', projectId: 'RD-001', category: categories[1], period: `${year}-03`, voucher: '凭 0305', amount: 1250000 },
      { id: 'F3', projectId: 'RD-002', category: categories[1], period: `${year}-03`, voucher: '凭 0308', amount: 870000 },
    ],
  };
  return { orders, tasks };
}
