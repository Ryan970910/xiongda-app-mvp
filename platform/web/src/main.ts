import {createApp} from 'vue'
import {createPinia} from 'pinia'
import {createRouter,createWebHashHistory} from 'vue-router'
import App from './App.vue'
import '../../../styles.css'
import '../../../header-options/review.css'
import './work.css'
const router=createRouter({history:createWebHashHistory(),routes:[{path:'/:pathMatch(.*)*',component:{render:()=>null}}]})
createApp(App).use(createPinia()).use(router).mount('#app')
