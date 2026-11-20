import { concepts, lettering, source, pick, select, serial } from './themes.js';

const ids = Object.keys(concepts);
function trial(side, id) {
  const c = concepts[id];
  return `<section class="trial"><header>${select(
    side,
    side === 'left' ? '左侧试办' : '右侧试办',
    ids.map((k) => [k, concepts[k].name]),
    id
  )}
    <a class="go" href="?ui=${id}#dashboard">独立打开 ↗</a></header><iframe title="${c.name}独立试办区" src="?ui=${id}&amp;trial=1#dashboard"></iframe></section>`;
}
export function gallery(p) {
  const id = Object.hasOwn(concepts, p.feature) ? p.feature : ids[0];
  const c = concepts[id];
  const mode = p.gallery || (new URL(location.href).searchParams.get('view') === 'type' ? 'type' : 'index');
  const toggles = `<div class="mode-switch">${pick('gallery', 'index', '浏览选集', mode)}${pick('gallery', 'type', '字形对照', mode)}${pick('gallery', 'pair', '双窗试办', mode)}</div>`;
  return `<div class="collection"><header class="collection-head"><div><p>科研财税政务协作　/　设计选集</p><h1>十种办事方式<span>.</span></h1></div>${toggles}</header>
    ${
      mode === 'pair'
        ? `<p class="trial-note">任选两种界面并排操作。两侧从同样的虚构资料开始，独立试办；更换该侧方案可重来。</p><div class="duet">${trial('left', p.left || 'specimen')}${trial('right', p.right || 'queue')}</div>`
        : mode === 'type'
          ? `<div class="font-index">${ids.map((k, i) => `<a data-work="${k}" href="?ui=${k}#dashboard"><span class="font-id">${serial(i + 1)} / ${concepts[k].reference}</span><h2>${concepts[k].name}</h2><span class="font-caption">${lettering[k]}</span><b>${concepts[k].action} ↗</b></a>`).join('')}</div>`
          : `<div class="showroom"><div class="feature" data-work="${id}"><a class="screen" href="?ui=${id}#dashboard" aria-label="试办${c.name}"><img src="./previews/${id}.webp" alt="${c.name}实际操作界面" width="880" height="550"></a>
      <div class="feature-caption"><div><small>字形　${lettering[id]}</small><h2>${c.name}</h2><p>${c.idea}</p>${source(c)}</div>
      <a class="enter" href="?ui=${id}#dashboard">开始试办 <b>↗</b></a></div></div>
      <nav class="works" aria-label="十套设计">${ids.map((key, i) => pick('feature', key, `<s>${serial(i + 1)}</s><span>${concepts[key].name}<small>${concepts[key].action}</small></span><i>↗</i>`, id)).join('')}</nav></div>`
    }
    </div>`;
}
