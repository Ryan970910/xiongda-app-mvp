<script setup lang="ts">
import {statusName} from './forms'
import type {Row} from './store'

defineProps<{rows: Row[]}>()
</script>

<template>
  <table v-if="rows.length" class="task-register">
    <thead>
      <tr><th scope="col">任务</th><th scope="col">服务事项</th><th scope="col">办理状态</th><th scope="col">截止日期</th></tr>
    </thead>
    <tbody>
      <tr v-for="task in rows" :key="task.id">
        <td class="task-subject">
          <a :href="'#/tasks/'+task.id" :aria-label="'查看'+task.title">{{task.title}}<span aria-hidden="true">›</span></a>
        </td>
        <td class="task-kind">{{task.kind}}</td>
        <td class="task-state"><span :class="['tag',task.status]">{{statusName(task.status)}}</span></td>
        <td class="task-due"><template v-if="task.deadline"><span>截止 </span><time :datetime="task.deadline">{{task.deadline}}</time></template><template v-else>—</template></td>
      </tr>
    </tbody>
  </table>
  <p v-else class="empty">当前条件下还没有任务。</p>
</template>
