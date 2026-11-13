let csrf='';
// The temporary single-project deployment intentionally has no backend.
// Local development and Vercel both render the original UI without API requests.
// Keep this isolated flag so backend integration can be restored later.
export const STATIC_PREVIEW = import.meta.env.VITE_STATIC_PREVIEW !== 'false';
const PREVIEW_ERROR = '현재 화면 미리보기 단계입니다. 로그인·등록·거래 등 데이터 기능은 아직 연결되지 않았습니다.';

export class ApiError extends Error{constructor(message:string,public status:number){super(message)}}
export async function api<T=any>(path:string,options:RequestInit={}):Promise<T>{
  const method=(options.method||'GET').toUpperCase();
  if(STATIC_PREVIEW){
    if(method==='GET' && path.startsWith('/listings?')){
      // Keep home and explore pages usable without inventing real listings.
      return {items:[], next_cursor:null, total_estimate:0} as T;
    }
    throw new ApiError(PREVIEW_ERROR, 503);
  }

  const h=new Headers(options.headers);
  if(options.body && !(options.body instanceof FormData))h.set('Content-Type','application/json');
  if(!['GET','HEAD'].includes(method)){h.set('X-CSRF-Token',csrf);if(method==='POST'&&!h.has('Idempotency-Key'))h.set('Idempotency-Key',crypto.randomUUID())}
  const r=await fetch('/api/v1'+path,{...options,headers:h,credentials:'include'});
  let data:any;try{data=await r.json()}catch{data={}}
  if(!r.ok)throw new ApiError(data?.error?.message||data?.detail||`HTTP ${r.status}`,r.status);
  if(data.csrf_token)csrf=data.csrf_token;
  return data as T;
}
export const body=(v:unknown):RequestInit=>({method:'POST',body:JSON.stringify(v)});
export const patch=(v:unknown):RequestInit=>({method:'PATCH',body:JSON.stringify(v)});
export const put=(v:unknown):RequestInit=>({method:'PUT',body:JSON.stringify(v)});
export const errorText=(e:unknown)=>e instanceof Error?e.message:'요청 중 문제가 발생했습니다.';

export function csrfToken(){return csrf}
export async function uploadPrivateFile(listingId:string,file:File){
  if(STATIC_PREVIEW)throw new ApiError(PREVIEW_ERROR,503);
  const form=new FormData();form.set('file',file,file.name);
  const r=await fetch('/api/v1/listings/'+encodeURIComponent(listingId)+'/assets/upload',{
    method:'POST',headers:{'X-CSRF-Token':csrf},credentials:'include',body:form});
  const data=await r.json().catch(()=>({}));
  if(!r.ok)throw new ApiError(data?.error?.message||'파일 업로드 실패',r.status);
  return data;
}
export async function downloadPrivateFile(assetId:string,filename:string){
  if(STATIC_PREVIEW)throw new ApiError(PREVIEW_ERROR,503);
  const ticket=await api<{ticket:string}>('/assets/'+encodeURIComponent(assetId)+'/download-intents',body({}));
  const r=await fetch('/api/v1/assets/redeem',{method:'POST',credentials:'include',
    headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({token:ticket.ticket})});
  if(!r.ok){const err=await r.json().catch(()=>({}));throw new ApiError(err?.error?.message||'파일 다운로드 실패',r.status)}
  const blob=await r.blob();const link=document.createElement('a');const url=URL.createObjectURL(blob);
  try{link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove()}
  finally{setTimeout(()=>URL.revokeObjectURL(url),15000)}
}

async function sha256File(file:File):Promise<string>{
  const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());
  return Array.from(new Uint8Array(digest)).map(x=>x.toString(16).padStart(2,'0')).join('');
}

export async function uploadSourceZip<T=any>(file:File):Promise<T>{
  if(STATIC_PREVIEW)throw new ApiError(PREVIEW_ERROR,503);
  if(file.size>4*1024*1024){
    const intent=await api<{upload_url:string,token:string,headers:Record<string,string>}>(
      '/listing-imports/zip/direct-intent',body({filename:file.name,size_bytes:file.size,checksum_sha256:await sha256File(file)}));
    const upload=await fetch(intent.upload_url,{method:'PUT',headers:intent.headers,body:file});
    if(!upload.ok)throw new ApiError('비공개 저장소 직접 업로드 실패 (CORS 및 저장소 설정 확인)',upload.status);
    return api<T>('/listing-imports/zip/direct-complete',body({token:intent.token}));
  }

  const form=new FormData();form.set('file',file,file.name);
  const r=await fetch('/api/v1/listing-imports/zip',{
    method:'POST',headers:{'X-CSRF-Token':csrf},credentials:'include',body:form});
  const data=await r.json().catch(()=>({}));
  if(!r.ok)throw new ApiError(data?.error?.message||data?.detail||`HTTP ${r.status}`,r.status);
  return data as T;
}
