<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref} from 'vue'
import {useRouter} from 'vue-router'
import {useWorkspace,type Row} from './store'
import {keyLabel,shown,statusName} from './forms'

const props=defineProps<{pid:number,templates:Row[]}>()
const api=useWorkspace(),base='/projects/'+props.pid+'/writing'
const info=ref<Row|null>(null),error=ref(''),message=ref(''),loading=ref(true)
const category=ref(''),variant=ref('')
const outlines=computed(()=>props.templates.filter(x=>x.category!=='pick'))
const kinds=computed(()=>Array.from(new Map(outlines.value.map(x=>[x.category,x.kind])).entries()))
const variants=computed(()=>outlines.value.filter(x=>x.category===(category.value||kinds.value[0]?.[0])))
const selected=computed(()=>variants.value.find(x=>x.id===variant.value)||variants.value[0])
const editor=ref<HTMLDialogElement>(),current=ref<Row|null>(null),layout=ref<Row>({})
const title=ref(''),values=ref<Record<string,string>>({}),dirty=ref(false),busy=ref(false),editError=ref('')
const targets=ref<Record<number,number>>({})

async function load(){
  try{info.value=await api.send(base);error.value=''}
  catch(e:any){error.value=e.message}
  finally{loading.value=false}
}
onMounted(load)
function canLeave(){return !editor.value?.open||!dirty.value||confirm('放弃尚未保存的修改？')}
const removeGuard=useRouter().beforeEach(()=>!busy.value&&canLeave())
function beforeUnload(e:BeforeUnloadEvent){if(editor.value?.open&&dirty.value){e.preventDefault();e.returnValue=''}}
onMounted(()=>window.addEventListener('beforeunload',beforeUnload))
onUnmounted(()=>{removeGuard();window.removeEventListener('beforeunload',beforeUnload)})
function initialValues(p:Row,fields:string[]){
  const d=p.details,period=[d.start,d.end].filter(Boolean).join(' 至 ')
  const basics=[p.name,p.code,d.leader,d.category,period].filter(Boolean).join(' · ')
  const team=(d.personnel||[]).map((x:Row)=>[x.name,x.responsibility].filter(Boolean).join(' · ')).join('\n')
  const plan=(d.milestones||[]).map((x:Row)=>[x.day,x.name,x.indicator].filter(Boolean).join(' · ')).join('\n')
  const defaults:Record<string,string>={
    '项目基本信息（项目名称、周期、项目负责人、项目类型）':basics,'项目基本情况':basics,'项目概述':basics,
    '项目清单':p.code+' '+p.name,'实施周期':period,'创新目标':d.objective,'项目创新点':d.innovation,
    '项目组主要人员及分工':team,'项目团队':team,'项目参与人员列表及情况说明':team,'项目进度安排':plan,
    '技术不确定性':d.uncertainty,'项目预算金额':String(p.budget)+' 元','项目经费预算':String(p.budget)+' 元'
  }
  return Object.fromEntries(fields.map(f=>[f,defaults[f]||'']))
}
function write(draft?:Row){
  const p=info.value?.project
  const outline=draft?.payload.layout||selected.value
  if(!p||!outline)return
  current.value=draft||null;layout.value=outline
  title.value=draft?.payload.title||[p.name,outline.kind].join(' · ').slice(0,128)
  values.value=draft?{...draft.payload.values}:initialValues(p,outline.fields)
  editError.value='';dirty.value=false;editor.value?.showModal()
}
function close(){
  if(!busy.value&&canLeave())editor.value?.close()
}
async function save(){
  if(busy.value)return
  busy.value=true;editError.value=''
  try{
    const d=current.value
    await api.send(base+'/drafts'+(d?'/'+d.id:''),d?'put':'post',{
      template:layout.value.id,title:title.value,values:values.value,revision:d?.revision})
    editor.value?.close();message.value='草稿已保存，可以继续编写。';await load()
  }catch(e:any){editError.value=e.message}finally{busy.value=false}
}
async function transfer(d:Row){
  const choices=info.value?.tasks||[]
  const target=targets.value[d.id]||(choices.length===1?choices[0].id:null)
  if(!target||busy.value)return
  busy.value=true;error.value=''
  try{
    await api.send(base+'/drafts/'+d.id+'/transfer','post',{task:target,revision:d.revision})
    message.value='已转入任务，可在「文书与材料」继续办理和送审。';await load()
  }catch(e:any){error.value=e.message}finally{busy.value=false}
}
async function download(path:string,name:string){
  try{await api.file(path,name+'.docx')}catch(e:any){error.value=e.message}
}
</script>

<template>
<a href="#/projects" class="text-link">← 研发项目</a>
<p v-if="error" class="error" role="alert">{{error}}</p>
<p v-if="loading" class="sub">正在读取项目材料…</p>
<template v-if="info">
  <div class="page-head"><div><h1>{{info.project.name}}</h1><p class="sub">项目编号 {{info.project.code}} · 负责人 {{info.project.details.leader}}</p></div></div>
  <div class="stack project-writing">
    <section class="panel panel-body">
      <h2>按大纲编写材料</h2>
      <div class="field-grid">
        <label>材料类型<select :value="category||kinds[0]?.[0]" @change="category=($event.target as HTMLSelectElement).value;variant=''"><option v-for="[key,name] in kinds" :key="key" :value="key">{{name}}</option></select></label>
        <label>大纲模板<select :value="selected?.id" @change="variant=($event.target as HTMLSelectElement).value"><option v-for="o in variants" :key="o.id" :value="o.id">{{o.name}}</option></select></label>
      </div>
      <template v-if="selected"><p>{{selected.scenario}}</p><details :key="selected.id"><summary>查看填写大纲（{{selected.fields.length}} 栏）</summary><ol><li v-for="f in selected.fields" :key="f">{{f}}</li></ol></details>
      <button v-if="info.can_write" class="button primary" @click="write()">按此大纲编写</button></template>
      <p v-if="!info.can_write" class="sub">{{info.project.details.closed?'此项目已结题。':'材料由获派的科研承办或协办填写。'}}</p>
    </section>
    <p v-if="message" role="status">{{message}}</p>
    <section v-if="info.can_write||info.drafts.length" class="panel panel-body">
      <h2>我的材料草稿</h2><p v-if="!info.drafts.length" class="sub">保存后，可在这里继续填写或下载 Word。</p>
      <article v-for="d in info.drafts" :key="d.id" class="writing-row">
        <h3>{{d.payload.title}}</h3><p class="sub">{{d.payload.layout.name}} · 草稿第 {{d.revision}} 版</p>
        <div class="toolbar"><button v-if="info.can_write" class="button" @click="write(d)">继续编写</button>
        <button class="text-link" @click="download(base+'/drafts/'+d.id+'/word',d.payload.title)">下载草稿 Word</button></div>
        <div v-if="info.can_write&&info.tasks.length" class="toolbar">
          <label>办理任务 <select :value="targets[d.id]||(info.tasks.length===1?info.tasks[0].id:'')" @change="targets[d.id]=Number(($event.target as HTMLSelectElement).value)"><option value="">请选择任务</option><option v-for="t in info.tasks" :key="t.id" :value="t.id">{{t.title}}</option></select></label>
          <button class="button" :disabled="busy||(!targets[d.id]&&info.tasks.length!==1)" @click="transfer(d)">转入任务</button>
        </div>
      </article>
      <p v-if="info.can_write&&info.drafts.length&&!info.tasks.length" class="sub">草稿已保存在本项目。要送审，请先接件；如尚未派单，请经理分派同一订单下的科研任务。</p>
    </section>
    <section class="panel panel-body"><h2>已进入任务的材料</h2><p v-if="!info.documents.length" class="sub">暂无本人可见的项目文书。</p>
      <article v-for="doc in info.documents" :key="doc.id" class="writing-row"><h3>{{doc.title}}</h3><p class="sub">{{doc.task_title}} · {{statusName(doc.status)}}</p>
        <div class="toolbar"><a :href="'#/tasks/'+doc.task+'?tab=documents'" class="text-link">进入任务办理</a>
        <button class="text-link" @click="download('/documents/'+doc.id+'/word',doc.title)">下载 Word</button></div></article>
    </section>
    <details class="panel panel-body"><summary>项目建档信息</summary><dl><dt>服务订单编号</dt><dd>{{info.project.order_id}}</dd><dt>客户编号</dt><dd>{{info.project.customer}}</dd><template v-for="(v,k) in info.project.details" :key="k"><dt>{{keyLabel(String(k))}}</dt>
      <dd v-if="Array.isArray(v)"><ul v-if="v.length"><li v-for="(item,i) in v" :key="i">{{typeof item==='object'?Object.values(item).join(' · '):item}}</li></ul><span v-else>—</span></dd>
      <dd v-else>{{v&&typeof v==='object'?Object.values(v).join(' · '):shown(v)||'—'}}</dd></template></dl></details>
  </div>
</template>
<dialog ref="editor" class="writing-editor" aria-labelledby="project-writing-title" @cancel.prevent="close()">
  <form @submit.prevent="save" @input="dirty=true">
    <div class="panel-head"><h2 id="project-writing-title">{{layout.kind}} · {{layout.name}}</h2><button type="button" class="button" @click="close()">关闭</button></div>
    <div class="panel-body"><label>材料标题<input v-model="title" required maxlength="128"></label>
      <label v-for="(f,i) in layout.fields" :key="f">{{Number(i)+1}}. {{f}}<textarea v-model="values[f]" rows="3" maxlength="10000"></textarea></label>
    </div>
    <footer class="writing-save"><p v-if="editError" class="error" role="alert">{{editError}}</p><button class="button primary" :disabled="busy">{{busy?'保存中…':'保存草稿'}}</button></footer>
  </form>
</dialog>
</template>
