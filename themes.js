export const concepts = {
  specimen: {
    name: '研发标本台',
    reference: 'Fabrica',
    slug: 'fabrica',
    art: 'specimen',
    action: '点选标注，查项目',
    idea: '将解剖图谱的定位针移到研发标本上，每个针位打开一项项目记录。'
  },
  queue: {
    name: '受理候场线',
    reference: 'Standby',
    slug: 'standby',
    art: 'print',
    action: '拖动票签，逐件受理',
    idea: '借用可拖动的排队机制。每张票就是一件任务，拉动队列便能逐件接办。'
  },
  arc: {
    name: '委托陈列馆',
    reference: 'Oeuvre',
    slug: 'oeuvre',
    art: 'optic',
    action: '拨开扇面，选择委托',
    idea: '把夜间展厅里的扇形卡组变成委托陈列，点一册即可查看关联事项。'
  },
  press: {
    name: '材料印刷间',
    reference: 'Tinta House',
    slug: 'tinta-house',
    art: 'print',
    action: '平移拼贴，抽取材料',
    idea: '以可平移的印刷拼贴组织各份底稿，抽出一张即可查材料索引。'
  },
  leaves: {
    name: '版本手卷',
    reference: 'The Long Light',
    slug: 'the-long-light',
    art: 'folio',
    action: '拖动页角，追溯提交',
    idea: '将分层纸景与翻书动作变为提交版次，可从书页直接进入对应底稿。'
  },
  glyph: {
    name: '字模检索室',
    reference: 'Lacuna',
    slug: 'lacuna',
    art: 'raster',
    action: '键入词片，检索底稿',
    idea: '用单色网点与等宽字模呈现档案。键入名称、材料或客户词片，索引就地收窄。'
  },
  ridge: {
    name: '时限风标',
    reference: 'ARÊTE',
    slug: 'arete',
    art: 'ridge',
    action: '拖动刻度，定位期限',
    idea: '将风中织物和时间变化转为办理期限刻度，可逐日定位实际事项。'
  },
  relay: {
    name: '协办星图',
    reference: 'Synapse',
    slug: 'synapse',
    art: null,
    action: '连接节点，处理补件',
    idea: '把紫色场域里的会话变成订单协办图，点选科研或财务节点追踪问题。'
  },
  optic: {
    name: '凭证显影室',
    reference: 'Ondine',
    slug: 'ondine',
    art: 'optic',
    action: '移动焦环，核验明细',
    idea: '将跟踪焦环用于凭证核验，沿光轨移动可切换金额、费用类别与所属项目。'
  },
  court: {
    name: '政务回廊',
    reference: 'Solano',
    slug: 'solano',
    art: 'court',
    action: '穿过门洞，进入业务',
    idea: '将日照庭院的房间导航转为业务空间，沿回廊选择订单、项目或交付。'
  }
};
export const designs = Object.fromEntries(Object.entries(concepts).map(([id, c]) => [id, [c.name]]));
export const lettering = {
  specimen: '站酷庆科黄油体',
  queue: '得意黑 / Barlow Condensed',
  arc: '刘建毛草',
  press: '站酷快乐体',
  leaves: '龙藏体',
  glyph: '缝合像素 12px',
  ridge: '马善政楷书',
  relay: '站酷小薇',
  optic: '霞鹜新晰黑 / 原创七段数字',
  court: '志莽行书'
};
export const legacy = {
  hall: 'glyph',
  intake: 'queue',
  review: 'leaves',
  archive: 'press',
  calendar: 'ridge',
  funds: 'optic',
  liaison: 'relay',
  guide: 'court',
  monitor: 'ridge',
  access: 'specimen',
  transit: 'court',
  proof: 'leaves',
  optics: 'optic',
  departures: 'queue',
  ledger: 'optic',
  strata: 'press',
  swiss: 'glyph',
  film: 'leaves',
  weave: 'relay',
  stage: 'arc'
};
export const sourceUrl = (c) => 'https://www.scrolltide.co/templates/' + c.slug;
export const safe = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]
  );
export const target = (page, id) => '#' + page + (id ? '/' + encodeURIComponent(id) : '');
export const openRecord = (label, page, id) =>
  `<a class="go" href="${target(page, id)}">${safe(label)} <span aria-hidden="true">↗</span></a>`;
export const art = (key, alt = '', klass = '') =>
  `<img class="plate ${klass}" alt="${safe(alt)}" src="./assets/${key}.webp" draggable="false">`;
export const pick = (key, value, label, active, klass = '') =>
  `<button type="button" class="choice ${klass}" data-set="${key}" data-value="${safe(value)}" aria-pressed="${String(value) === String(active)}">${label}</button>`;
export const select = (key, label, rows, value) =>
  `<label class="selector"><span>${label}</span><select data-pick="${key}">${rows.map(([id, name]) => `<option value="${safe(id)}" ${String(id) === String(value) ? 'selected' : ''}>${safe(name)}</option>`).join('')}</select></label>`;
export const source = (c) =>
  `<a class="source" href="${sourceUrl(c)}" target="_blank" rel="noopener">Scrolltide · ${c.reference} ↗</a>`;
export const yen = (n) =>
  new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(n / 100);
export const serial = (n) => String(n).padStart(2, '0');
export const empty = (message) => `<p class="empty">${safe(message)}</p>`;
export function at(value, list) {
  return Math.max(0, Math.min(list.length - 1, Number(value) || 0));
}
export function steps(key, index, count, previous = '上一项', next = '下一项') {
  return `<div class="steppers"><button aria-label="${previous}" data-set="${key}" data-value="${Math.max(0, index - 1)}" ${index === 0 ? 'disabled' : ''}>←</button><output>${serial(index + 1)} / ${serial(count)}</output><button aria-label="${next}" data-set="${key}" data-value="${Math.min(index + 1, count - 1)}" ${index >= count - 1 ? 'disabled' : ''}>→</button></div>`;
}
