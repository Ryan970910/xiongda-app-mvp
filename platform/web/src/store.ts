import axios from 'axios'
import {defineStore} from 'pinia'
export type Row=Record<string,any>
const client=axios.create({baseURL:'/api/v1',timeout:60000})
export const useWorkspace=defineStore('session',()=>{
  function get(){return JSON.parse(sessionStorage.getItem('local-session')||'null')}
  function clear(){sessionStorage.removeItem('local-session')}
  function remember(s:Row){sessionStorage.setItem('local-session',JSON.stringify(s))}
  let refresh:Promise<void>|null=null
  async function send(path:string,method='get',data?:any,blob=false,retry=true):Promise<any>{
    const current=get()
    try{
      const res=await client.request({url:path,method,data,responseType:blob?'blob':'json',headers:current?{Authorization:'Bearer '+current.access_token}:{}})
      return blob?res:res.data.data
    }catch(err:any){
      if(err.response?.status===401&&current&&retry&&!path.startsWith('/auth/')){
        try{
          refresh??=client.post('/auth/refresh',{refresh_token:current.refresh_token}).then(r=>remember(r.data.data)).finally(()=>{refresh=null})
          await refresh
        }catch{clear();window.dispatchEvent(new Event('session-ended'));throw Error('登录已过期，请重新登录。')}
        return send(path,method,data,blob,false)
      }
      let body=err.response?.data
      if(body instanceof Blob){try{body=JSON.parse(await body.text())}catch{body=null}}
      const fields=Array.isArray(body?.data)?body.data.map((v:Row)=>v.field.replace('body.','')+' '+v.message).join('、'):''
      throw Error([body?.message||'工作台连接失败，请检查启动窗口。',fields].filter(Boolean).join(' · '))
    }
  }
  async function file(path:string,fallback:string){
    const r=await send(path,'get',undefined,true)
    const head=r.headers['content-disposition']||''
    const encoded=head.match(/filename\*=UTF-8''([^;]+)/i)
    const link=document.createElement('a');link.download=encoded?decodeURIComponent(encoded[1]):fallback
    const url=URL.createObjectURL(r.data);link.href=url;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  return {get,clear,remember,send,file}
})
