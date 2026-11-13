import {useActionDialog} from './ActionDialog';
import React,{useEffect,useState} from 'react';
import {ArrowRight,ArrowUpRight,Bell,Check,CheckCircle2,ChevronLeft,ChevronRight,ImagePlus,LockKeyhole,MessageSquare,MonitorPlay,ShieldAlert,Trash2,ExternalLink} from 'lucide-react';
import {api,put,body,errorText} from './api';
import {Link,useNavigate} from 'react-router-dom';
import {useNotifications,NoticeItem} from './NotificationState';

type Media={id:string;url:string;caption:string;width:number;height:number;position:number};
type Showcase={demo_url:string|null;video_url:string|null;highlights:string[];media:Media[];seller_provided:boolean;demo_not_verified:boolean};
const blank:Showcase={demo_url:null,video_url:null,highlights:[],media:[],seller_provided:true,demo_not_verified:true};

export function ShowcaseViewer({listingId,includeDemo}:{listingId:string;includeDemo:boolean}){
 const [data,setData]=useState<Showcase|null>(null),[chosen,setChosen]=useState(0);
 useEffect(()=>{let mounted=true;api<Showcase>(`/listings/${listingId}/showcase${includeDemo?'?include_demo=true':''}`).then(x=>{if(mounted){setData(x);setChosen(0)}}).catch(()=>{});return()=>{mounted=false}},[listingId,includeDemo]);
 if(!data || (!data.media.length&&!data.demo_url&&!data.video_url&&!data.highlights.length))return null;
 const item=data.media[chosen]||data.media[0];
 return <section className="experience-viewer" aria-label="프로젝트 미리보기">
   {item&&<><div className="experience-stage"><img src={item.url} alt={item.caption||'프로젝트 시연 화면'} loading="lazy"/>{item.caption&&<span>{item.caption}</span>}</div>
     {data.media.length>1&&<div className="experience-thumbnails">{data.media.map((m,i)=><button key={m.id} type="button" className={i===chosen?'active':''} onClick={()=>setChosen(i)} title={`화면 ${i+1}`}><img src={m.url} alt={`프로젝트 화면 ${i+1}`}/></button>)}</div>}</>}
   {(data.demo_url||data.video_url)&&<div className="experience-links">{data.demo_url&&<a href={data.demo_url} target="_blank" rel="noopener noreferrer nofollow"><MonitorPlay size={17}/> 시연 사이트 열기 <ArrowUpRight size={16}/></a>}{data.video_url&&<a href={data.video_url} target="_blank" rel="noopener noreferrer nofollow"><ExternalLink size={16}/> 시연 영상 보기 <ArrowUpRight size={16}/></a>}</div>}
   {!!data.highlights.length&&<div className="experience-features"><h3>주요 기능 · 판매자 제공 정보</h3><ul>{data.highlights.map((h,i)=><li key={i}><Check size={15}/>{h}</li>)}</ul></div>}
   <p className="experience-note"><ShieldAlert size={15}/> 이미지·설명·외부 링크는 판매자가 등록한 자료입니다. 플랫폼은 실제 동작을 보증하지 않습니다.</p>
 </section>
}

export function ShowcaseEditor({listingId,includeDemo,onDirtyChange}:{listingId:string;includeDemo:boolean;onDirtyChange?:(dirty:boolean)=>void}){
 const dialog=useActionDialog();
 const [data,setData]=useState<Showcase>(blank),[demo,setDemo]=useState(''),[video,setVideo]=useState(''),[highlights,setHighlights]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 const [uploadKey,setUploadKey]=useState(0);
 async function refresh(mediaOnly=false){const r=await api<Showcase>(`/listings/${listingId}/showcase${includeDemo?'?include_demo=true':''}`);setData(r);if(!mediaOnly){setDemo(r.demo_url||'');setVideo(r.video_url||'');setHighlights(r.highlights.join('\n'))}}
 useEffect(()=>{refresh().catch(e=>setError(errorText(e)))},[listingId]);
 async function save(){setBusy(true);setError('');setMessage('');try{await api(`/listings/${listingId}/showcase`,put({demo_url:demo.trim()||null,video_url:video.trim()||null,highlights:highlights.split('\n').map(s=>s.trim()).filter(Boolean)}));await refresh();onDirtyChange?.(false);setMessage('시연 정보가 저장됐습니다. 매물 공개 전 관리자 검토가 필요합니다.')}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 async function upload(e:React.ChangeEvent<HTMLInputElement>){const file=e.target.files?.[0];if(!file)return;setBusy(true);setError('');setMessage('');try{const form=new FormData();form.set('file',file,file.name);await api(`/listings/${listingId}/media`,{method:'POST',body:form});await refresh(true);setMessage('화면 이미지가 추가됐습니다. 변경된 매물은 관리자 재검토 대상입니다.')}catch(e){setError(errorText(e))}finally{setBusy(false);setUploadKey(k=>k+1)}}
 async function updatePhoto(id:string,caption:string,setCover=false){setBusy(true);setError('');try{await api(`/listings/${listingId}/media/${id}`,{method:'PATCH',body:JSON.stringify({caption,set_cover:setCover})});await refresh(true);setMessage('화면 정보가 변경되었습니다. 관리자 재검토가 필요합니다.')}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 async function remove(id:string){if(!await dialog.confirm({title:'이미지를 삭제할까요?',description:'현재 프로젝트에 등록된 화면 이미지가 삭제됩니다.',danger:true,confirmText:'이미지 삭제'}))return;setBusy(true);setError('');try{await api(`/listings/${listingId}/media/${id}`,{method:'DELETE'});await refresh(true)}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 return <section className="experience-editor"><div className="experience-title"><div><p className="eyebrow">PROJECT SHOWCASE</p><h2>프로젝트를 직접 보여주세요</h2><p>이미지와 시연 링크를 추가하면 구매자가 프로젝트를 더 쉽게 이해합니다.</p></div><span>공개 전 검토</span></div>
  <div className="experience-photo-editor">{data.media.map(m=><div key={m.id} className="experience-photo"><img src={m.url} alt={m.caption||'등록된 프로젝트 화면'}/><button type="button" className="experience-delete" aria-label="이미지 삭제" onClick={()=>remove(m.id)} disabled={busy}><Trash2 size={16}/></button><div className="experience-photo-controls"><button type="button" disabled={busy||m.position===0} onClick={()=>updatePhoto(m.id,m.caption,true)}>{m.position===0?'대표 이미지':'대표로 설정'}</button><button type="button" disabled={busy} onClick={async()=>{const value=await dialog.ask({title:'이미지 설명 수정',description:'프로젝트 화면에서 무엇을 보여주는지 설명해 주세요.',defaultValue:m.caption,maximum:140,confirmText:'설명 저장'});if(value!==null)updatePhoto(m.id,value)}}>{m.caption?'설명 수정':'설명 추가'}</button></div></div>)}
  {data.media.length<8&&<label className="experience-upload"><ImagePlus size={25}/><strong>화면 이미지 추가</strong><span>JPG, PNG, WebP · 4MB 이하 · 최대 8장</span><input key={uploadKey} type="file" accept="image/png,image/jpeg,image/webp" onChange={upload} disabled={busy}/></label>}</div>
  <div className="experience-input-grid"><label>실행 가능한 데모 URL <span>(선택)</span><input className="input" type="url" placeholder="https://example.com" value={demo} onChange={e=>{setDemo(e.target.value);onDirtyChange?.(true)}}/></label><label>시연 영상 <span>(YouTube / Vimeo)</span><input className="input" type="url" placeholder="https://www.youtube.com/watch?v=..." value={video} onChange={e=>{setVideo(e.target.value);onDirtyChange?.(true)}}/></label></div>
  <label className="experience-lines">구매자에게 보여줄 주요 기능 <span>(한 줄에 하나 · 최대 8개)</span><textarea className="input textarea" rows={4} value={highlights} placeholder="로그인 및 회원 관리\n대시보드\n통계 내보내기" onChange={e=>{setHighlights(e.target.value);onDirtyChange?.(true)}}/></label>
  <div className="experience-edit-footer"><p><LockKeyhole size={15}/> 이미지는 안전한 이미지 형식으로 변환되며 소스코드는 공개되지 않습니다.</p><button className="btn primary" type="button" disabled={busy} onClick={save}>{busy?'저장 중…':'미리보기 정보 저장'} <ArrowRight size={17}/></button></div>
  {error&&<p role="alert" className="experience-error">{error}</p>}{message&&<p className="experience-success">{message}</p>}
 {dialog.dialog}</section>
}

type Inquiry={id:string;listing_id:string;listing_title?:string;question:string;visibility:'PUBLIC'|'PRIVATE';answer:string|null;answered_at:string|null;created_at:string;is_mine:boolean;role?:'SELLER'|'BUYER'};
const shortDate=(value:string)=>new Date(value).toLocaleDateString('ko-KR');

export function InquiryPanel({listingId,includeDemo,userId,sellerId}:{listingId:string;includeDemo:boolean;userId:string|null;sellerId:string}){
 const [items,setItems]=useState<Inquiry[]>([]),[question,setQuestion]=useState(''),[visibility,setVisibility]=useState<'PUBLIC'|'PRIVATE'>('PUBLIC'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[reply,setReply]=useState<Record<string,string>>({});
 async function refresh(){const r=await api<{items:Inquiry[]}>(`/listings/${listingId}/inquiries${includeDemo?'?include_demo=true':''}`);setItems(r.items)}
 useEffect(()=>{refresh().catch(()=>{})},[listingId,includeDemo,userId]);
 async function ask(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{await api(`/listings/${listingId}/inquiries`,body({question,visibility}));setQuestion('');await refresh()}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 async function answer(id:string){setBusy(true);setError('');try{await api(`/inquiries/${id}/answer`,body({answer:reply[id]}));setReply(r=>({...r,[id]:''}));await refresh()}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 return <section className="detail-section inquiries"><h2><MessageSquare size={21}/> 프로젝트 문의</h2><p>구매를 결정하기 전에 프로젝트의 상태를 물어보세요. 공개 질문은 다른 구매자에게도 도움이 됩니다.</p>
 {!items.length&&<div className="inquiry-empty">아직 등록된 질문이 없습니다. 첫 번째 질문을 남겨보세요.</div>}
 {items.map(r=><article key={r.id} className="inquiry-item"><div className="inquiry-meta"><span>{r.visibility==='PRIVATE'?<><LockKeyhole size={13}/> 비공개 질문</>:'공개 질문'}</span><span>{shortDate(r.created_at)}</span></div><p className="inquiry-question">{r.question}</p>{r.answer?<div className="inquiry-answer"><strong><CheckCircle2 size={15}/> 판매자 답변</strong><p>{r.answer}</p></div>:<p className="inquiry-pending">판매자 답변 대기 중</p>}
 {userId===sellerId&&!r.answer&&<div className="inquiry-reply"><textarea className="input textarea" rows={3} maxLength={2000} placeholder="구매자가 이해할 수 있게 답변해주세요." value={reply[r.id]||''} onChange={e=>setReply(v=>({...v,[r.id]:e.target.value}))}/><button type="button" className="btn outline" disabled={busy||(reply[r.id]||'').trim().length<2} onClick={()=>answer(r.id)}>답변 등록</button></div>}
 </article>)}
 {userId&&userId!==sellerId?<form className="inquiry-form" onSubmit={ask}><h3>판매자에게 질문하기</h3><div className="inquiry-choice"><label><input type="radio" checked={visibility==='PUBLIC'} onChange={()=>setVisibility('PUBLIC')}/> 공개 질문</label><label><input type="radio" checked={visibility==='PRIVATE'} onChange={()=>setVisibility('PRIVATE')}/> 비공개 질문</label></div><textarea className="input textarea" rows={4} minLength={10} maxLength={1500} placeholder="어떤 기능까지 완성됐나요? 실행하려면 어떤 서비스가 필요한가요?" value={question} onChange={e=>setQuestion(e.target.value)} required/><p className="muted">개인 연락처나 외부 링크 없이 질문해주세요. 문의가 등록되면 판매자에게 알림이 전달됩니다.</p><button className="btn primary" disabled={busy||question.trim().length<10} type="submit">질문 등록 <ArrowRight size={17}/></button></form>:!userId&&<p className="inquiry-login"><Link to="/login">로그인하면 판매자에게 문의할 수 있습니다.</Link></p>}
 {error&&<p role="alert" className="experience-error">{error}</p>}
 </section>
}

export function InquiryInbox(){const [items,setItems]=useState<Inquiry[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[answer,setAnswer]=useState<Record<string,string>>({});
 async function refresh(){const x=await api<{items:Inquiry[]}>('/inquiries/inbox');setItems(x.items)}
 useEffect(()=>{refresh().catch(e=>setError(errorText(e)))},[]);
 async function send(id:string){setBusy(true);setError('');try{await api(`/inquiries/${id}/answer`,body({answer:answer[id]}));await refresh()}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 return <div className="dashboard-panel inquiry-inbox"><div className="dashboard-panel-head"><h2>프로젝트 문의함</h2><p>매물별 질문과 답변을 확인합니다. 비공개 질문은 당사자에게만 공개됩니다.</p></div>{!items.length&&<p className="muted">아직 보낸 문의나 받은 문의가 없습니다.</p>}{items.map(item=><article className="inquiry-item" key={item.id}><div className="inquiry-meta"><span>{item.role==='SELLER'?'받은 문의':'내 질문'} · {item.visibility==='PRIVATE'?'비공개':'공개'}</span><span>{shortDate(item.created_at)}</span></div><Link to={`/listings/${item.listing_id}`} className="inquiry-listing-link">{item.listing_title||'프로젝트'} <ArrowUpRight size={15}/></Link><p className="inquiry-question">{item.question}</p>{item.answer?<div className="inquiry-answer"><strong>판매자 답변</strong><p>{item.answer}</p></div>:item.role==='SELLER'?<div className="inquiry-reply"><textarea className="input textarea" rows={3} maxLength={2000} placeholder="답변을 작성하세요." value={answer[item.id]||''} onChange={e=>setAnswer(x=>({...x,[item.id]:e.target.value}))}/><button className="btn outline" type="button" disabled={busy||(answer[item.id]||'').trim().length<2} onClick={()=>send(item.id)}>답변 등록</button></div>:<span className="muted">답변을 기다리고 있습니다.</span>}</article>)}{error&&<p role="alert" className="experience-error">{error}</p>}</div>
}

function noticePath(item:NoticeItem){if(item.resource_type==='listing')return `/listings/${item.resource_id}`;if(item.resource_type==='inquiry')return '/dashboard?tab=inquiries';if(item.resource_type==='offer')return '/dashboard?tab=offers';if(item.resource_type==='transaction')return `/transactions/${item.resource_id}`;if(item.resource_type==='agent_action')return '/operations?tab=approvals';return '/dashboard'}
export function NotificationBell(){const {unread}=useNotifications();return <Link className="notification-bell" to="/notifications" aria-label={unread?`읽지 않은 알림 ${unread}개`:'알림 확인'} title="알림 확인"><Bell size={19}/>{unread>0&&<span>{unread>99?'99+':unread}</span>}</Link>}
export function NotificationCenter(){
 const nav=useNavigate();const {items,unread,hasMore,loading,loadingMore,error,mark,markAll,loadMore}=useNotifications();
 const [onlyUnread,setOnlyUnread]=useState(false),[busy,setBusy]=useState(false);
 async function all(){setBusy(true);try{await markAll()}finally{setBusy(false)}}
 async function open(n:NoticeItem){if(!n.read_at&&!(await mark(n.id)))return;nav(noticePath(n))}
 const visible=onlyUnread?items.filter(n=>!n.read_at):items;
 return <section className="dashboard-panel notice-center"><div className="notification-top"><div><h2>알림</h2><p>문의, 제안, 검토 결과와 거래 진행 상황을 확인하세요.</p></div><button className="btn outline" type="button" disabled={!unread||busy} onClick={all}>모두 읽음 처리 {unread>0&&`(${unread})`}</button></div>
 <div className="notification-toolbar"><label className="checkline"><input type="checkbox" checked={onlyUnread} onChange={e=>setOnlyUnread(e.target.checked)}/> 읽지 않은 알림만</label><Link to="/settings">알림 수신 설정</Link></div>
 {loading&&!items.length&&<p role="status" className="muted">알림을 불러오는 중입니다…</p>}
 {!visible.length&&!loading&&<div className="empty-state-compact">{onlyUnread?'읽지 않은 알림이 없습니다.':'새로운 알림이 없습니다.'}</div>}
 {visible.map(n=><div className={'notification-row '+(!n.read_at?'unread':'')} key={n.id}><div className="notification-icon"><Bell size={17}/></div><div><button className="notification-title" type="button" onClick={()=>open(n)}>{n.title}</button><p>{shortDate(n.created_at)}</p></div>{!n.read_at&&<button className="notification-mark" type="button" onClick={()=>mark(n.id)}>읽음</button>}</div>)}
 {hasMore&&<div className="notification-more"><button type="button" className="btn outline" disabled={loadingMore} onClick={()=>void loadMore()}>{loadingMore?'더 불러오는 중…':'이전 알림 더 보기'}</button></div>}
 {error&&<p role="alert" className="experience-error">{error}</p>}
 </section>
}
export function NotificationPreferences(){const [enabled,setEnabled]=useState(true),[configured,setConfigured]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState(false);
 async function refresh(){const r=await api<{email_enabled:boolean;email_delivery_configured:boolean}>('/notifications/preferences');setEnabled(r.email_enabled);setConfigured(r.email_delivery_configured)}
 useEffect(()=>{refresh().catch(e=>setError(errorText(e)))},[]);
 async function preference(next:boolean){setBusy(true);setError('');setSaved(false);try{await api('/notifications/preferences',put({email_enabled:next}));setEnabled(next);setSaved(true)}catch(e){setError(errorText(e))}finally{setBusy(false)}}
 return <section className="settings-section"><h2>알림 설정</h2><p>사이트 안의 알림은 항상 받을 수 있고, 이메일 알림만 별도로 선택할 수 있습니다.</p><label className="settings-toggle"><input type="checkbox" checked={enabled} disabled={busy} onChange={e=>preference(e.target.checked)}/> 주요 알림 이메일로 받기</label><p className="fine">{configured?'서버에 이메일 설정이 있습니다. 실제 발송은 별도 워커 실행에 따라 달라집니다.':'현재 이메일 발송 기능이 설정되지 않았습니다. 사이트 내 알림은 정상 작동합니다.'}</p>{saved&&<p role="status" className="experience-success">설정을 저장했습니다.</p>}{error&&<p role="alert" className="experience-error">{error}</p>}</section>
}
