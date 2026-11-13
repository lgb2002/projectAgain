import React,{useEffect,useId,useRef,useState} from 'react';
import {Link,useNavigate,useParams} from 'react-router-dom';
import {ArrowLeft,ArrowRight,ChevronLeft,CheckCircle2,Save,RotateCcw,AlertTriangle} from 'lucide-react';
import {api,body,patch,errorText} from './api';
import {Listing,categories,lifecycles,rights,lists,money} from './types';
import {ImportPanel,SourceImport} from './ImportPanel';
import {ShowcaseEditor} from './MarketplaceExperience';
import {useActionDialog} from './ActionDialog';

const empty={title:'',description:'',category:'web_app',lifecycle_status:'UNLAUNCHED',sale_rights_type:'ASSET_TRANSFER_ONLY',inventory_mode:'ONE_TIME',price_krw:'100000',tech_stack:'',included_assets:'',excluded_assets:'',known_defects:'',required_services:'',monthly_cost_estimate_krw:'0',handover_days_estimate:'7',seller_support_days:'7',has_revenue:false,revenue_krw_claimed:'',rights_attested:false,is_demo:true};
type FormData=typeof empty;
const stepNames=['기본 정보','제공 자산·상태','권리·인수 조건','등록 전 확인'];
const isNumber=(v:string,min:number,max:number)=>v.trim()!==''&&Number.isFinite(Number(v))&&Number(v)>=min&&Number(v)<=max;
function validate(f:FormData,index:number){
 if(index===0){if(!f.title.trim())return '프로젝트 이름을 입력해 주세요.';if(f.description.trim().length<30)return '프로젝트 설명을 30자 이상 입력해 주세요.';if(!isNumber(f.price_krw,1,1e9))return '판매 희망가를 1원 이상 10억 원 이하로 입력해 주세요.'}
 if(index===1){if(lists(f.included_assets).length===0)return '구매자에게 제공할 자산을 한 가지 이상 입력해 주세요.';if(!isNumber(f.monthly_cost_estimate_krw,0,1e9))return '월 운영비를 올바르게 입력해 주세요.'}
 if(index===2){if(!isNumber(f.handover_days_estimate,0,3650)||!isNumber(f.seller_support_days,0,3650))return '인수·지원 기간을 0~3650일 사이로 입력해 주세요.';if(f.has_revenue&&!isNumber(f.revenue_krw_claimed,0,1e13))return '판매자가 주장하는 매출을 올바르게 입력해 주세요.';if(!f.rights_attested)return '판매 권리 확인 항목을 체크해 주세요.'}
 return '';
}
function F({label,children,help}:{label:string;children:React.ReactNode;help?:string}){
 const id=useId();const content=React.isValidElement<{id?:string; 'aria-describedby'?:string}>(children)?React.cloneElement(children,{id:children.props.id||id,'aria-describedby':help?`${id}-help`:undefined}):children;
 return <div className="field"><label className="label" htmlFor={id}>{label}</label>{content}{help&&<p className="fine" id={`${id}-help`}>{help}</p>}</div>;
}
function T({value,onChange,...props}:React.InputHTMLAttributes<HTMLInputElement>){return <input className="input" value={value} onChange={onChange} {...props}/>}
function TA({value,onChange,...props}:React.TextareaHTMLAttributes<HTMLTextAreaElement>){return <textarea className="input textarea" value={value} onChange={onChange} {...props}/>}
function S({value,onChange,children,disabled,id,...rest}:{value:string;onChange:(e:React.ChangeEvent<HTMLSelectElement>)=>void;children:React.ReactNode;disabled?:boolean;id?:string;'aria-describedby'?:string}){return <select id={id} {...rest} className="input select" value={value} onChange={onChange} disabled={disabled}>{children}</select>}
function O({values}:{values:Record<string,string>}){return <>{Object.entries(values).map(([k,v])=><option key={k} value={k}>{v}</option>)}</>}

export function ListingEditor({edit=false}:{edit?:boolean}){
 const {id}=useParams();const nav=useNavigate();const dialog=useActionDialog();
 // The key is scoped to the authenticated account, preventing drafts appearing for another user on the same browser.
 const [account,setAccount]=useState<string|null>(null);
 const [supportConfirmed,setSupportConfirmed]=useState(false);
 const [form,setForm]=useState<FormData>(empty),[sourceImport,setSourceImport]=useState<SourceImport|null>(null);
 const [current,setCurrent]=useState<Listing|null>(null),[step,setStep]=useState(0),[err,setErr]=useState('');
 const [busy,setBusy]=useState(false),[ready,setReady]=useState(false),[savedAt,setSavedAt]=useState<string|null>(null);
 const [resumeInfo,setResumeInfo]=useState('');const [importLost,setImportLost]=useState(false);const [draftConflict,setDraftConflict]=useState(false);const alertRef=useRef<HTMLDivElement|null>(null);
 const draftKey=account?`projectagain:listing-draft:v1:${account}:${edit?id:'new'}`:null;
 const changedRef=useRef(false);const baseline=useRef<FormData>({...empty});
 useEffect(()=>{let active=true;setReady(false);
  (async()=>{
   try{
    const who=await api<{id:string}>('/auth/me');if(!active)return;
    setAccount(who.id);
    let initial={...empty};let listing:Listing|null=null;
    if(edit&&id){listing=await api<Listing>(`/listings/${id}`);if(!active)return;
     setCurrent(listing);initial={title:listing.title,description:listing.description,category:listing.category,lifecycle_status:listing.lifecycle_status,sale_rights_type:listing.sale_rights_type,inventory_mode:listing.inventory_mode,price_krw:String(listing.price_krw),tech_stack:listing.tech_stack.join(', '),included_assets:listing.included_assets.join('\n'),excluded_assets:listing.excluded_assets.join('\n'),known_defects:listing.known_defects.join('\n'),required_services:listing.required_services.join('\n'),monthly_cost_estimate_krw:String(listing.monthly_cost_estimate_krw??0),handover_days_estimate:String(listing.handover_days_estimate??7),seller_support_days:String(listing.seller_support_days??0),has_revenue:listing.has_revenue,revenue_krw_claimed:String(listing.revenue_krw_claimed??''),rights_attested:true,is_demo:listing.is_demo};
    }
    baseline.current={...initial};const key=`projectagain:listing-draft:v1:${who.id}:${edit?id:'new'}`;
    try{const raw=localStorage.getItem(key);if(raw){const saved=JSON.parse(raw);if(saved.form&&typeof saved.form.title==='string'){
     // Do not silently overwrite a changed server version. Editing must use the latest server revision.
     if(!edit||saved.serverVersion===listing?.version){initial={...initial,...saved.form};setResumeInfo(saved.hadImport?'작성 내용은 복구했지만 GitHub·ZIP 원본 연결은 다시 진행해야 합니다.':'이 브라우저에 보관했던 작성 내용을 복구했습니다.');setImportLost(Boolean(saved.hadImport));setSavedAt(saved.savedAt||null)}
     else{setDraftConflict(true);setResumeInfo('서버에 더 새로운 매물 수정 내용이 있어 이전 브라우저 임시본은 적용하지 않았습니다. 새 수정이 시작되기 전까지 기존 임시본도 보존합니다.');}
    }}}catch{setResumeInfo('브라우저 임시 저장본을 읽을 수 없어 서버 내용을 표시합니다.')}
    if(active){setForm(initial);setSupportConfirmed(edit);setReady(true)}
   }catch(e){if(active)setErr(errorText(e))}
  })();return()=>{active=false};
 },[edit,id]);
 useEffect(()=>{if(!ready||!draftKey||draftConflict)return;
  const timer=window.setTimeout(()=>{try{const now=new Date().toISOString();localStorage.setItem(draftKey,JSON.stringify({form,savedAt:now,serverVersion:current?.version??null,hadImport:!!sourceImport||importLost}));setSavedAt(now)}catch{setResumeInfo('이 브라우저에서 임시 저장을 사용할 수 없습니다. 작성 중 페이지를 닫지 마세요.')}},600);
  return()=>window.clearTimeout(timer);
 },[ready,draftKey,form,current?.version,draftConflict,sourceImport,importLost]);
 useEffect(()=>{if(!ready)return;function protect(e:BeforeUnloadEvent){if(changedRef.current){e.preventDefault();e.returnValue=''}}window.addEventListener('beforeunload',protect);return()=>window.removeEventListener('beforeunload',protect)},[ready]);
 useEffect(()=>{if(err)alertRef.current?.focus()},[err]);
 function set(k:keyof FormData,value:string|boolean){if(k==='seller_support_days')setSupportConfirmed(false);setDraftConflict(false);changedRef.current=true;setErr('');setForm(s=>({...s,[k]:value}))}
 async function imported(src:SourceImport|null){
  if(src&&([form.description,form.included_assets,form.tech_stack].some(s=>s.trim()))){
   const accept=await dialog.confirm({title:'자동 분석 결과를 입력할까요?',description:'설명, 기술 정보, 제공 자산, 외부 서비스 항목의 현재 내용이 분석 결과로 바뀝니다. 다른 항목과 기존 작성본은 브라우저에 보관됩니다.',confirmText:'분석 내용 적용'});
   if(!accept)return;
  }
  setSourceImport(src);if(src){setImportLost(false);setDraftConflict(false);const a=src.analysis;setForm(f=>({...f,title:f.title||src.source_label.split('/').pop()?.replace(/\.zip$/i,'')||'',description:a.description_suggestion,tech_stack:a.tech_stack.join(', '),included_assets:a.included_assets_suggestion.join('\n'),excluded_assets:a.excluded_assets_suggestion.join('\n'),required_services:a.possible_services.join(', ')}));changedRef.current=true;setResumeInfo('자동 분석 결과가 적용되었습니다. 수정할 수 있으며, 실제 작동·판매 권리는 직접 확인해야 합니다.')}
 }
 function goto(target:number){if(target>step){for(let i=0;i<target;i++){const problem=validate(form,i)||(i===2&&Number(form.seller_support_days)>0&&!supportConfirmed?'사후 지원 범위와 기간에 동의해 주세요.':'');if(problem){setStep(i);setErr(`다음 단계로 넘어가기 전에 확인해 주세요. ${problem}`);return}}}setStep(target);setErr('')}
 async function discard(){if(!await dialog.confirm({title:'임시 작성본을 지울까요?',description:'브라우저에 보관된 수정 내용을 지우고 다시 시작합니다. 서버에 이미 저장한 매물은 삭제하지 않습니다.',danger:true,confirmText:'임시 내용 삭제'}))return;
  if(draftKey)localStorage.removeItem(draftKey);changedRef.current=false;setForm({...baseline.current});setStep(0);setSavedAt(null);setSourceImport(null);setImportLost(false);setDraftConflict(false);setSupportConfirmed(false);setResumeInfo('브라우저에 보관된 작성 내용을 지웠습니다.')
 }
 async function submit(){if(importLost){setErr('분석된 소스 연결은 새로고침 시 복구되지 않습니다. GitHub 또는 ZIP 소스를 다시 가져오거나 아래에서 연결 없이 진행하도록 선택하세요.');setStep(0);return}for(let i=0;i<3;i++){const problem=validate(form,i)||(i===2&&Number(form.seller_support_days)>0&&!supportConfirmed?'사후 지원 범위와 기간에 동의해 주세요.':'');if(problem){setStep(i);setErr(problem);return}}
  setBusy(true);setErr('');const data={title:form.title.trim(),description:form.description.trim(),category:form.category,lifecycle_status:form.lifecycle_status,sale_rights_type:form.sale_rights_type,inventory_mode:form.inventory_mode,price_krw:Number(form.price_krw),tech_stack:lists(form.tech_stack),included_assets:lists(form.included_assets),excluded_assets:lists(form.excluded_assets),known_defects:lists(form.known_defects),required_services:lists(form.required_services),monthly_cost_estimate_krw:Number(form.monthly_cost_estimate_krw),handover_days_estimate:Number(form.handover_days_estimate),seller_support_days:Number(form.seller_support_days),has_revenue:form.has_revenue,revenue_krw_claimed:form.has_revenue&&form.revenue_krw_claimed?Number(form.revenue_krw_claimed):null,rights_attested:form.rights_attested,is_demo:form.is_demo,...(!edit&&sourceImport?{import_id:sourceImport.id}:{})};
  try{if(edit&&current){await api(`/listings/${current.id}`,patch({...data,inventory_mode:undefined,has_revenue:undefined,revenue_krw_claimed:undefined,is_demo:undefined,expected_version:current.version}));changedRef.current=false;if(draftKey)localStorage.removeItem(draftKey);nav('/dashboard?tab=listings')}
   else{const listing=await api<Listing>('/listings',body(data));changedRef.current=false;if(draftKey)localStorage.removeItem(draftKey);nav('/sell/'+listing.id+'/complete')}
  }catch(e){setErr(errorText(e))}finally{setBusy(false)}
 }
 if(!ready)return <main className="page-container narrow"><p role="status">매물 정보를 준비하고 있습니다…</p>{err&&<div role="alert">{err}</div>}<Link to="/dashboard">내 활동으로</Link></main>;
 return <main className="page-container narrow"><Link className="back-link" to="/dashboard"><ArrowLeft size={16}/> 내 활동으로</Link>
  <div className="editor-titlebar"><div><p className="eyebrow">PROJECT REGISTRATION</p><h1>{edit?'매물 정보 수정':'내 프로젝트 등록'}</h1><p className="subheading">현재 상태와 인수 조건을 정확히 알려 주세요. 입력 내용은 이 브라우저에 자동으로 임시 보관됩니다.</p></div><button className="btn outline" onClick={discard} type="button"><RotateCcw size={16}/> 임시본 지우기</button></div>
  <div className="draft-status" role="status"><Save size={16}/>{savedAt?`이 브라우저에 임시 저장됨 · ${new Date(savedAt).toLocaleTimeString('ko-KR')}`:'작성 내용을 임시 보관합니다.'}<span>서버 저장은 마지막 단계에서 완료됩니다.</span></div>
  {resumeInfo&&<div className="notice neutral" role="status">{resumeInfo}{importLost&&<button className="btn outline" type="button" onClick={()=>{setImportLost(false);setResumeInfo('원본 소스 연결 없이 등록합니다. 소스를 다시 연결하려면 GitHub 또는 ZIP 분석을 진행하세요.')}}>원본 없이 진행</button>}</div>}
  {!edit&&<ImportPanel value={sourceImport} onChange={imported}/>}
  {edit&&id&&<section className="editor-showcase"><h2>사진·시연 관리</h2><p className="muted">사진과 시연 정보는 저장된 매물의 별도 항목입니다. 수정된 내용은 기존 심사 정책에 따라 다시 검토됩니다.</p><ShowcaseEditor listingId={id} includeDemo={Boolean(current?.is_demo)}/></section>}
  {!edit&&<div className="notice neutral">사진과 시연 링크는 기본 정보를 저장한 다음 화면에서 추가합니다. <strong>관리자 검토 요청 전까지 매물은 공개되지 않습니다.</strong></div>}
  <div className="wizard-progress" aria-label="매물 등록 진행"><div className="wizard-progress-fill" style={{width:`${(step+1)/4*100}%`}}/></div>
  <nav className="wizard-steps" aria-label="매물 등록 단계">{stepNames.map((name,i)=><button type="button" key={name} className={i===step?'active':''} aria-current={i===step?'step':undefined} onClick={()=>goto(i)}><span>{i+1}단계</span>{name}</button>)}</nav>
  <section className="editor-panel"><p className="wizard-kicker">전체 4단계 중 {step+1}단계</p>
  {step===0&&<div className="form-stack"><h2>어떤 프로젝트인가요?</h2>
   <F label="프로젝트 이름"><T value={form.title} onChange={e=>set('title',e.target.value)} maxLength={120} placeholder="예: 소형 AI 예약 관리 웹앱"/></F>
   <F label="상세 설명 · 최소 30자"><TA rows={7} value={form.description} onChange={e=>set('description',e.target.value)} placeholder="누구에게 필요한 프로젝트인지, 현재 어떤 기능이 동작하는지 알려 주세요."/></F>
   <div className="two-fields"><F label="카테고리"><S value={form.category} onChange={e=>set('category',e.target.value)}><O values={categories}/></S></F><F label="현재 개발 상태"><S value={form.lifecycle_status} onChange={e=>set('lifecycle_status',e.target.value)}><O values={lifecycles}/></S></F></div>
   <F label="판매 희망가 (원)" help="주요 가격대는 5만~100만 원이며, 실제 결제는 아직 지원하지 않습니다."><T type="number" min="1" max="1000000000" value={form.price_krw} onChange={e=>set('price_krw',e.target.value)}/></F>
  </div>}
  {step===1&&<div className="form-stack"><h2>구매자가 무엇을 받나요?</h2>
   <F label="개발 기술 (쉼표로 구분)"><T value={form.tech_stack} onChange={e=>set('tech_stack',e.target.value)} placeholder="React, FastAPI, PostgreSQL"/></F>
   <F label="제공되는 자산 · 한 줄에 한 항목"><TA rows={4} value={form.included_assets} onChange={e=>set('included_assets',e.target.value)} placeholder={'소스코드\n설치 및 배포 문서'}/></F>
   <F label="제외되는 자산"><TA rows={3} value={form.excluded_assets} onChange={e=>set('excluded_assets',e.target.value)} placeholder={'개인 API 키\n기존 사용자 데이터'}/></F>
   <F label="알려진 결함·미완성 기능"><TA rows={3} value={form.known_defects} onChange={e=>set('known_defects',e.target.value)} placeholder="결제 기능 미완성"/></F>
   <F label="필요한 외부 서비스"><T value={form.required_services} onChange={e=>set('required_services',e.target.value)} placeholder="서버 호스팅, 데이터베이스, 외부 API"/></F>
   <F label="예상 월 운영비 (원)"><T type="number" min="0" value={form.monthly_cost_estimate_krw} onChange={e=>set('monthly_cost_estimate_krw',e.target.value)}/></F>
  </div>}
  {step===2&&<div className="form-stack"><h2>판매 권리와 인수 조건</h2>
   <F label="판매 권리 유형"><S value={form.sale_rights_type} onChange={e=>set('sale_rights_type',e.target.value)}><O values={rights}/></S></F>
   <F label="판매 방식"><S value={form.inventory_mode} disabled={edit} onChange={e=>set('inventory_mode',e.target.value)}><option value="ONE_TIME">한 번만 판매</option><option value="REPEAT_LICENSE">비독점 사용권 반복 판매</option></S></F>
   <div className="two-fields"><F label="예상 인수인계 (일)"><T type="number" min="0" value={form.handover_days_estimate} onChange={e=>set('handover_days_estimate',e.target.value)}/></F><F label="사후 지원 기간"><S value={form.seller_support_days} onChange={e=>set('seller_support_days',e.target.value)}><option value="0">지원 없음</option><option value="7">7일 · 기본 3건 (추천)</option><option value="14">14일 · 기본 5건</option><option value="30">30일 · 기본 10건</option>{![0,7,14,30].includes(Number(form.seller_support_days))&&<option value={form.seller_support_days}>기존 설정 {form.seller_support_days}일 (수정 전 보존)</option>}</S></F></div>
   {Number(form.seller_support_days)>0&&<label className="checkline"><input type="checkbox" checked={supportConfirmed} onChange={e=>setSupportConfirmed(e.target.checked)}/>지원 기간과 무료 문의 건수는 구매자와 최종 합의한 조건으로 적용되며, 신규 개발이나 운영 대행은 포함되지 않음을 확인합니다.</label>}
   <label className="checkline"><input type="checkbox" checked={form.has_revenue} disabled={edit} onChange={e=>set('has_revenue',e.target.checked)}/>현재 또는 과거 매출이 있나요?</label>
   {form.has_revenue&&<F label="판매자가 주장하는 매출 (원)" help="이 금액은 별도의 검증 전까지 판매자 진술로만 표시됩니다."><T type="number" disabled={edit} min="0" value={form.revenue_krw_claimed} onChange={e=>set('revenue_krw_claimed',e.target.value)}/></F>}
   <div className="notice neutral"><AlertTriangle size={17}/> 외부 이미지·폰트·오픈소스·계정의 권리는 별도일 수 있습니다. 실제 권리 이전에는 계약이 필요합니다.</div>
   <label className="checkline"><input type="checkbox" checked={form.rights_attested} onChange={e=>set('rights_attested',e.target.checked)}/>명시한 자산을 판매하거나 사용 허락할 권리가 있음을 확인합니다.</label>
  </div>}
  {step===3&&<div className="form-stack"><h2>구매자에게 이렇게 소개됩니다</h2>
   <div className="listing-preview"><div className="listing-preview-head"><div><span>{categories[form.category]} · {lifecycles[form.lifecycle_status]}</span><h3>{form.title}</h3></div><strong>{money(Number(form.price_krw))}</strong></div><p>{form.description}</p><h4>포함되는 자산</h4><ul>{lists(form.included_assets).map((a,i)=><li key={i}>{a}</li>)}</ul><h4>알려진 문제</h4>{lists(form.known_defects).length?<ul>{lists(form.known_defects).map((a,i)=><li key={i}>{a}</li>)}</ul>:<p>판매자가 별도로 등록한 문제가 없습니다. 문제가 없음을 검증한 것은 아닙니다.</p>}<p className="fine">판매 권리: {rights[form.sale_rights_type]} · 인계 예상 {form.handover_days_estimate}일</p></div>
   {sourceImport&&<p className="import-note">정적 분석을 통해 가져온 자료: {sourceImport.source_label}. 실제 동작·권리는 별도 확인 전입니다.</p>}
   <label className="checkline"><input type="checkbox" checked={form.is_demo} disabled={edit} onChange={e=>set('is_demo',e.target.checked)}/>시연용 프로젝트로 등록</label>
   <p className="fine">다음 화면에서 사진·시연 정보를 추가한 뒤 검토 요청할 수 있습니다. 관리자 승인 후에만 탐색에 공개됩니다.</p>
  </div>}
  {err&&<div className="notice error" role="alert" ref={alertRef} tabIndex={-1}>{err}</div>}
  <div className="wizard-controls"><button className="btn outline" disabled={step===0} onClick={()=>goto(Math.max(0,step-1))}><ChevronLeft size={16}/> 이전</button>
   {step<3?<button className="btn primary" onClick={()=>goto(step+1)}>다음 단계 <ArrowRight size={17}/></button>:<button className="btn primary" disabled={busy} onClick={submit}>{busy?'저장 중…':edit?'수정 저장':'초안 저장하고 계속'} <CheckCircle2 size={17}/></button>}
  </div></section>{dialog.dialog}
 </main>;
}

/** Post-save completion screen. URL is reload-safe: a seller can return and finish later. */
export function ListingFinish(){const {id}=useParams();const nav=useNavigate();const [listing,setListing]=useState<Listing|null>(null);
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[err,setErr]=useState(''),[showcaseDirty,setShowcaseDirty]=useState(false);
 useEffect(()=>{if(!id)return;let active=true;setLoading(true);Promise.all([api<Listing>(`/listings/${id}`),api<{id:string}>('/auth/me')])
  .then(([x,who])=>{if(active){if(x.seller_id!==who.id){setErr('이 프로젝트의 판매자만 등록을 마무리할 수 있습니다.');setListing(null)}else setListing(x)}}).catch(e=>{if(active)setErr(errorText(e))}).finally(()=>{if(active)setLoading(false)});
  return()=>{active=false}},[id]);
 async function requestReview(){if(!listing)return;setBusy(true);setErr('');try{
  const latest=await api<Listing>(`/listings/${listing.id}`);
  await api(`/listings/${latest.id}`,patch({status:'PENDING_REVIEW',expected_version:latest.version}));
  nav('/dashboard?tab=listings');
 }catch(e){setErr(errorText(e))}finally{setBusy(false)}}
 if(loading)return <main className="page-container narrow"><p role="status">매물 정보를 불러오는 중입니다…</p></main>;
 if(!listing)return <main className="page-container narrow"><div role="alert" className="notice error">{err||'매물을 불러올 수 없습니다.'}</div><Link to="/dashboard">내 프로젝트로 돌아가기</Link></main>;
 return <main className="page-container narrow registration-finish"><div className="finish-heading"><CheckCircle2 size={29}/><div><p className="eyebrow">매물 초안 저장 완료</p><h1>프로젝트 소개를 마무리하세요</h1><p>매물은 아직 공개되지 않았습니다. 이미지·시연 정보를 추가한 후 검토를 요청할 수 있습니다.</p></div></div>
 <ol className="finish-steps"><li className="done">기본 정보와 권리 조건 저장</li><li className="current">사진·데모·주요 기능 추가 <span>(선택)</span></li><li>관리자 검토 요청</li></ol>
 <ShowcaseEditor listingId={listing.id} includeDemo={listing.is_demo} onDirtyChange={setShowcaseDirty}/>
 {showcaseDirty&&<div role="status" className="notice neutral">시연 링크 또는 주요 기능에 저장하지 않은 변경 내용이 있습니다. 위의 '미리보기 정보 저장'을 먼저 눌러 주세요.</div>}
 {err&&<div className="notice error" role="alert">{err}</div>}
 <div className="finish-actions"><Link to={`/listings/${listing.id}${listing.is_demo?'?demo=1':''}`} className="btn outline">매물 정보 확인</Link>
 <button type="button" className="btn primary" disabled={busy||showcaseDirty||!['DRAFT','PAUSED'].includes(listing.status)} onClick={requestReview}>{busy?'요청 중…':listing.status==='PENDING_REVIEW'?'검토 대기 중':'관리자 검토 요청'} <ArrowRight size={17}/></button></div>
 <p className="fine">나중에 완료하려면 <Link to="/dashboard?tab=listings">내 프로젝트</Link>에서 해당 매물을 다시 열 수 있습니다.</p></main>
}
