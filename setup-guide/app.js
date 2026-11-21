import { questions, applicable, makePlan } from './questions.js';

const app = document.querySelector('#app');
const storage = 'xiongda-preparation-v1';
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let answers = {}, checked = {}, current = 'stage', result = false;
try {
  const saved=JSON.parse(sessionStorage.getItem(storage) || '{}');
  for(const q of questions) if(q.options.some(o=>o[0]===saved.answers?.[q.id])) answers[q.id]=saved.answers[q.id];
  for(const [id,on] of Object.entries(saved.checked || {})) if(on===true) checked[id]=true;
  if(applicable(answers).some(q=>q.id===saved.current)) current=saved.current;
  result=saved.result===true && applicable(answers).every(q=>answers[q.id]);
} catch {}
function save(){
  try{sessionStorage.setItem(storage,JSON.stringify({answers,checked,current,result}));}catch{}
}
function label(q){return q.options.find(o=>o[0]===answers[q.id])?.[1] || '尚未选择';}
function focusTitle(){app.querySelector('[data-focus]')?.focus({preventScroll:true});}
function renderQuestion(){
  const path=applicable(answers), index=path.findIndex(q=>q.id===current), q=path[index], past=path.slice(0,index);
  app.innerHTML=`<div class="layout"><form class="card" id="quiz"><div class="question-head"><span class="eyebrow">第 ${index+1} 题 · ${q.label}</span><div class="meter" aria-hidden="true">${path.map((_,i)=>'<i class="'+(i<=index?'on':'')+'"></i>').join('')}</div></div>
    <fieldset aria-describedby="hint"><legend tabindex="-1" data-focus>${q.title}</legend><p class="hint" id="hint">${q.hint}</p>
    <div class="options">${q.options.map(([id,text,detail])=>`<label class="choice"><input type="radio" required name="answer" value="${id}" ${answers[q.id]===id?'checked':''}><span><strong>${text}</strong>${detail?`<small>${detail}</small>`:''}</span></label>`).join('')}</div></fieldset>
    <div class="actions">${index?'<button type="button" class="btn" data-back>上一步</button>':'<span></span>'}<button class="btn primary" type="submit" id="next">${index===path.length-1?'生成我的清单':'下一题 →'}</button></div></form>
    <aside class="side"><h2>你的选择</h2>${past.length?`<ul>${past.map(item=>`<li><small>${item.label}</small><span>${label(item)}</span></li>`).join('')}</ul>`:'<p>已回答的内容会显示在这里。最多六题。</p>'}<p>只用选择选项。答案只保存在这个浏览器标签页的会话里。</p></aside></div>`;
}
function updateAnswer(id,value){
  if(answers[id]===value)return;
  answers[id]=value;checked={};
  const visible=new Set(applicable(answers).map(q=>q.id));
  for(const q of questions)if(!visible.has(q.id))delete answers[q.id];
}
function renderStep(step,index){
  return `<article class="step"><h3><span class="num">${String(index+1).padStart(2,'0')}</span>${step.title}</h3><p class="who">找谁办 · ${step.who}</p>
    <ol>${step.actions.map(s=>`<li>${esc(s)}</li>`).join('')}</ol><label class="done"><input type="checkbox" data-done="${step.id}" ${checked[step.id]?'checked':''}><span><strong>办好标志</strong>　${esc(step.done)}</span></label>
    ${step.link?`<p class="source"><a href="${step.link[1]}" target="_blank" rel="noopener">${step.link[0]} ↗</a></p>`:''}</article>`;
}
const reply = '我现在准备到这一步了：\n① 使用的人和时间：____\n② 负责环境的单位／联系人岗位：____；存放地区和测试网址：____\n③ 文件名称和盖章单位：____；签章平台和测试是否开通：____\n还不知道的地方可写“待确认”。';
function renderResult(){
  const plan=makePlan(answers),items=applicable(answers);
  const group=(title,steps,offset)=>`<h2 class="section-title">${title}<span>${steps.length} 件</span></h2>${steps.map((s,i)=>renderStep(s,offset+i)).join('')}`;
  app.innerHTML=`<section class="result-head"><p class="eyebrow">你的准备清单</p><h2 tabindex="-1" data-focus>${plan.headline}</h2><p>${plan.summary}</p>
    <div class="actions"><button class="btn primary" data-download>下载文字清单</button><button class="btn" data-print>打印或存为 PDF</button><button class="btn" data-edit>修改答案</button></div></section>
    ${group('现在可以做',plan.now,0)}${plan.later.length?group('后面再安排',plan.later,plan.now.length):''}
    <section class="send"><h2>可以直接发给对方的话</h2>${[...plan.messages,{who:'办好后回复开发人员',text:reply}].map((m,i)=>`<article class="msg"><h3>${m.who}</h3><p>${esc(m.text)}</p><button class="btn" data-copy="${i}">复制这段话</button> <span class="notice" role="status"></span></article>`).join('')}
    <p class="note">账号密码、应用密钥、身份证和真实印章文件，请由单位授权人员通过官方渠道保管和提交。</p></section>
    <details class="summary"><summary>回看我的 ${items.length} 个答案</summary><ul>${items.map(q=>`<li>${q.label} · ${label(q)}</li>`).join('')}</ul></details>`;
}
function render(moveFocus=false){
  if(result)renderResult();else renderQuestion();
  if(moveFocus){window.scrollTo(0,0);focusTitle();}
}
function asText(){
  const plan=makePlan(answers);
  const steps=rows=>rows.map(s=>`${checked[s.id]?'[已办]':'[待办]'} ${s.title}\n找谁办：${s.who}\n${s.actions.map((v,i)=>`${i+1}. ${v}`).join('\n')}\n办好标志：${s.done}${s.link?'\n'+s.link.join(' '):''}`).join('\n\n');
  return ['科研财税协同 · 上线准备清单',plan.headline,plan.summary,'我的选择',...applicable(answers).map(q=>q.label+'：'+label(q)),
    '现在可以做',steps(plan.now),...(plan.later.length?['后面再安排',steps(plan.later)]:[]),'可以转发的话',...plan.messages.map(m=>m.who+'\n'+m.text),'回复开发人员',reply].join('\n\n');
}
app.addEventListener('change',e=>{
  const el=e.target;
  if(el.matches('[data-done]')){checked[el.dataset.done]=el.checked;save();return;}
  if(el.name==='answer'){
    updateAnswer(current,el.value);save();
    const path=applicable(answers),index=path.findIndex(q=>q.id===current);
    document.querySelector('#next').textContent=index===path.length-1?'生成我的清单':'下一题 →';
    const meter=app.querySelector('.meter');
    meter.innerHTML=path.map((_,i)=>'<i class="'+(i<=index?'on':'')+'"></i>').join('');
  }
});
app.addEventListener('submit',e=>{
  if(e.target.id!=='quiz')return;
  e.preventDefault();
  const val=new FormData(e.target).get('answer');
  if(!questions.find(q=>q.id===current).options.some(o=>o[0]===val))return;
  updateAnswer(current,val);
  const path=applicable(answers), index=path.findIndex(q=>q.id===current);
  if(index===path.length-1){const missed=path.find(q=>!answers[q.id]);if(missed)current=missed.id;else result=true;}
  else current=path[index+1].id;
  save();render(true);
});
app.addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.hasAttribute('data-back')){
    const path=applicable(answers);
    current=path[Math.max(0,path.findIndex(q=>q.id===current)-1)].id;
    save();render(true);
  }else if(b.hasAttribute('data-edit')){
    current='stage';result=false;save();render(true);
  }else if(b.hasAttribute('data-print'))window.print();
  else if(b.hasAttribute('data-download')){
    const url=URL.createObjectURL(new Blob(['\uFEFF',asText()],{type:'text/plain;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download='上线准备清单.txt';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }else if(b.hasAttribute('data-copy')){
    const text=b.closest('.msg').querySelector('p').textContent, status=b.nextElementSibling;
    try{await navigator.clipboard.writeText(text);status.textContent='已复制';}
    catch{let field=b.parentNode.querySelector('textarea');if(!field){field=document.createElement('textarea');field.className='copy-manual';field.readOnly=true;field.setAttribute('aria-label','可手动复制的内容');b.parentNode.append(field);}field.value=text;field.focus();field.select();status.textContent='已选中，可手动复制';}
  }
});
render();
