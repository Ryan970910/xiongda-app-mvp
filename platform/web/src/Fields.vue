<script setup lang="ts">
import {computed} from 'vue'
import {keyLabel,shown,today} from './forms'
import type {Row} from './store'
const props=defineProps<{schema:Row,schemas:Row,model:Row,choices:Record<string,Row[]>,hidden?:string[]}>()
const norm=(s:Row):Row=>s?.$ref?props.schemas[s.$ref.split('/').pop()!]:s
const propType=(s:Row)=>norm(s.anyOf?.find((x:Row)=>x.type!=='null')||s)
const fields=computed(()=>Object.entries(props.schema.properties||{}).filter(([k])=>!props.hidden?.includes(k)&&k!=='revision') as [string,Row][])
function required(k:string){return (props.schema.required||[]).includes(k)}
function format(k:string,s:Row){if(k.includes('password'))return 'password';if(k==='month')return 'month';if(k==='due')return 'date';if(s.format==='date-time')return 'datetime-local';if(s.format==='date')return 'date';if(s.type==='integer'||s.type==='number')return 'number';return 'text'}
function write(k:string,s:Row,event:Event){const target=event.target as HTMLInputElement;const schema=propType(s);if(schema.type==='boolean')props.model[k]=target.checked;else if(target.value==='')delete props.model[k];else props.model[k]=schema.type==='integer'?Number(target.value):target.value}
function options(k:string,s:Row){return props.choices[k]||s.enum?.map((v:any)=>({id:v,name:shown(v)}))}
function blank(s:Row):Row{const out:Row={};for(const [k,x] of Object.entries(s.properties||{}) as [string,Row][]){const v=propType(x);if(x.default!=null)out[k]=x.default;else if(v.type==='array')out[k]=[];else if(v.format==='date'&&s.required?.includes(k))out[k]=today();else if(v.enum)out[k]=v.enum[0]}return out}
</script>
<template><div class="field-grid"><template v-for="[k,raw] in fields" :key="k"><template v-for="s in [propType(raw)]" :key="k">
<fieldset v-if="s.type==='array' && norm(s.items).type==='object'" class="wide"><legend>{{keyLabel(k)}}</legend><div v-for="(item,i) in model[k]" :key="i" class="repeat"><Fields :schema="norm(s.items)" :schemas="schemas" :model="item" :choices="choices"/><button type="button" class="text-link" @click="model[k].splice(i,1)">移除此项</button></div><button type="button" class="button" @click="(model[k]??=[]).push(blank(norm(s.items)))">＋ 添加{{k==='projects'?'项目':k==='roles'?'岗位':keyLabel(k)}}</button></fieldset>
<fieldset v-else-if="s.type==='object'&&s.properties" class="wide"><legend>{{keyLabel(k)}}</legend><Fields :schema="s" :schemas="schemas" :model="model[k]??(model[k]=blank(s))" :choices="choices"/></fieldset>
<label v-else-if="s.type==='array'"><span>{{keyLabel(k)}}（可多选）</span><select multiple :value="model[k]" @change="model[k]=Array.from(($event.target as HTMLSelectElement).selectedOptions,o=>norm(s.items).type==='integer'?Number(o.value):o.value)"><option v-for="o in options(k,norm(s.items))||[]" :value="o.id" :key="o.id">{{o.name}}</option></select></label>
<label v-else-if="s.type==='boolean'" class="check-field"><input type="checkbox" :checked="model[k]??raw.default" @change="write(k,raw,$event)"> {{keyLabel(k)}}</label>
<label v-else-if="options(k,s)"><span>{{keyLabel(k)}}{{required(k)?' *':''}}</span><select :required="required(k)" :value="model[k]??raw.default??''" @change="write(k,raw,$event)"><option value="">请选择</option><option v-for="o in options(k,s)" :key="o.id" :value="o.id">{{o.name}}</option></select></label>
<label v-else :class="{wide:(s.maxLength||0)>=400}"><span>{{keyLabel(k)}}{{required(k)?' *':''}}</span><textarea v-if="(s.maxLength||0)>=400" :value="model[k]??''" :required="required(k)" :maxlength="s.maxLength" rows="3" @input="write(k,raw,$event)"></textarea><input v-else :type="format(k,s)" :step="s.type==='number'?'any':undefined" :value="model[k]??raw.default??''" :maxlength="s.maxLength" :minlength="s.minLength" :required="required(k)" :min="s.minimum" :max="s.maximum" @input="write(k,raw,$event)"></label>
</template></template></div></template>
