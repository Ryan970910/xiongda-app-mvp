<script setup lang="ts">
import type {Row} from './store'
import {shown,statusName} from './forms'
defineProps<{cols:[string,string][],rows:Row[],empty?:string}>()
</script>
<template><div v-if="rows.length" class="table-wrap"><table><thead><tr><th v-for="c in cols" :key="c[0]">{{c[1]}}</th><th v-if="$slots.default">办理</th></tr></thead><tbody><tr v-for="(r,i) in rows" :key="r.id??i"><td v-for="[key] in cols" :key="key"><span v-if="key==='status'" class="tag">{{statusName(r[key])}}</span><template v-else>{{shown(r[key]??r.details?.[key]??r.payload?.[key])||'—'}}</template></td><td v-if="$slots.default"><slot :row="r"/></td></tr></tbody></table></div><p v-else class="empty">{{empty||'当前条件下还没有记录。'}}</p></template>
