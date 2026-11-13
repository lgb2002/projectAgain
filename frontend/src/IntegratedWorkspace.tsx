import React,{useCallback,useEffect,useState} from 'react';
import {Link,useNavigate,useParams} from 'react-router-dom';
import {api,body,errorText} from './api';
import {money,rights} from './types';

type Support={days:number;included_case_limit:number;scope_codes:string[];reply_goal_hours:number;is_reply_goal_guaranteed:false;exceptions_note:string};
type Terms={schema_version:2;price_krw:number;rights_type:string;included_assets:string[];excluded_assets:string[];handover_days:number;support:Support;buyer_conditions_note:string};
type Proposal={id:string;proposed_by:string;offered_price_krw:number;status:string;version:number;terms:Terms|Record<string,unknown>;expires_at:string;created_at:string;legacy_terms:boolean;diff_from_previous:Record<string,{before:unknown;after:unknown}>};
type Thread={id:string;listing_id:string;status:string;buyer_id:string;seller_id:string;last_offer_id:string;offers:Proposal[];terms_template:Terms};
const daysMap:Record<number,number>={0:0,7:3,14:5,30:10};
const labels:Record<string,string>={price_krw:'제안 금액',rights_type:'권리 유형',included_assets:'포함 자산',excluded_assets:'제외 자산',handover_days:'인계 기간',support:'사후 지원',buyer_conditions_note:'특약 및 요청 사항'};
const scopeLabels:Record<string,string>={SETUP_GUIDANCE:'설치 및 설정',EXISTING_FUNCTION_GUIDANCE:'기존 기능',CODE_STRUCTURE_GUIDANCE:'코드 구조'};
const fmt=(x:string)=>new Date(x).toLocaleString('ko-KR');
const readable=(x:unknown)=>typeof x==='object'?JSON.stringify(x,null,2):String(x??'없음');

export function OfferNegotiation(){
 const {id}=useParams();const nav=useNavigate();const [thread,setThread]=useState<Thread|null>(null);const [draft,setDraft]=useState<Terms|null>(null);const [expiry,setExpiry]=useState(7);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[accepted,setAccepted]=useState(''),[confirmed,setConfirmed]=useState(false);
 const refresh=useCallback(async()=>{const t=await api<Thread>(`/offer-threads/${id}`);setThread(t);setDraft(old=>old||structured(t.offers.at(-1)?.terms,t.terms_template));},[id]);
 useEffect(()=>{refresh().catch(e=>setError(errorText(e)))},[refresh]);
 const last=thread?.offers.at(-1);const mine=last&&last.proposed_by===thread?.buyer_id?'구매자':'판매자';
 const [me,setMe]=useState('');useEffect(()=>{api<{id:string}>('/auth/me').then(r=>setMe(r.id)).catch(()=>{})},[]);
 const mayReply=!!last&&last.proposed_by!==me&&last.status==='PENDING'&&thread?.status==='UNRESOLVED';
 async function send(action:'counter'|'accept'|'decline'){
  if(!last||!thread)return;setBusy(true);setError('');try{
   if(action==='accept'){
    if(!confirmed){setError('변경된 가격·자산·지원 조건 및 시연 안내를 확인해 주세요.');return}
    const t=await api<{id:string}>(`/offer-threads/${thread.id}/accept`,body({expected_version:last.version}));setAccepted(t.id);nav('/transactions/'+t.id);return;
   }
   if(action==='decline'){await api(`/offers/${last.id}/decline`,body({expected_version:last.version}))}
   else if(draft){await api(`/offer-threads/${thread.id}/counter`,body({offered_price_krw:Number(draft.price_krw),terms:draft,
       expires_at:new Date(Date.now()+expiry*86400000).toISOString(),expected_version:last.version}))}
   setConfirmed(false);setDraft(null);await refresh();
  }catch(e){setError(errorText(e));if((e as {status?:number}).status===409){setDraft(null);await refresh().catch(()=>{})}}
  finally{setBusy(false)}
 }
 return <main className="page-container narrow v12-page"><Link to="/dashboard?tab=offers" className="back-link">내 제안함으로</Link><header className="v12-head"><p className="eyebrow">NEGOTIATION · DEMO</p><h1>구매 조건 협상</h1><p>가격뿐 아니라 자산·권리·판매자 지원 범위를 함께 확인하세요. 실제 결제나 법적 이전은 발생하지 않습니다.</p></header>
 {error&&<p className="v12-error" role="alert">{error}</p>}{accepted&&<p>시연 거래 {accepted}가 시작됐습니다.</p>}
 {!thread?<p>협상 내용을 확인하고 있습니다.</p>:<>
  <div className="v12-current"><span>현재 제안 · {thread.status}</span><strong>{money(last?.offered_price_krw||0)}</strong><small>제안자: {mine} · 만료: {last?fmt(last.expires_at):'-'}</small></div>
  <h2>협상 타임라인</h2><ol className="v12-timeline">{thread.offers.map((offer,i)=><li key={offer.id}><div className="v12-msg"><div><strong>{offer.proposed_by===thread.buyer_id?'구매자':'판매자'} · 제안 {i+1}</strong><small>{fmt(offer.created_at)} · {offer.status}</small></div><h3>{money(offer.offered_price_krw)}</h3>{offer.legacy_terms?<p className="v12-warning">기존 자유 형식 조건입니다. 새 약정으로 자동 변환되지 않습니다. 역제안할 때 모든 범위를 다시 확인하세요.</p>:<div className="v12-summary"><span>권리: {rights[(offer.terms as Terms).rights_type]||'별도 확인'}</span><span>인계 {(offer.terms as Terms).handover_days}일</span><span>지원 {(offer.terms as Terms).support.days}일 · {(offer.terms as Terms).support.included_case_limit}건</span></div>}{Object.keys(offer.diff_from_previous).length>0&&<details><summary>이전 제안과 변경된 조건 {Object.keys(offer.diff_from_previous).length}개</summary><div className="v12-differences">{Object.entries(offer.diff_from_previous).map(([key,v])=><div key={key}><strong>{labels[key]||key}</strong><span><del>{readable(v.before)}</del><b>{readable(v.after)}</b></span></div>)}</div></details>}</div></li>)}</ol>
  {mayReply&&<section className="v12-edit"><h2>이 조건에 답변하기</h2><p>역제안은 새로운 협상 기록으로 저장됩니다. 상대방이 최종 조건을 다시 확인해야 수락할 수 있습니다.</p>
  {draft&&<TermsEditor terms={draft} onChange={setDraft} availableAssets={thread.terms_template.included_assets}/>}<label>응답 기한<select className="input select" value={expiry} onChange={e=>setExpiry(Number(e.target.value))}>{[1,3,7,14].map(n=><option key={n} value={n}>{n}일</option>)}</select></label>
  <label className="v12-check"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> 최종 제안의 가격·포함/제외 자산·권리·지원 약정이 시연용임을 확인했습니다.</label>
  {last.legacy_terms&&<p className="v12-warning">기존 조건은 명시적으로 검토 후 V2 역제안하는 것을 권장합니다.</p>}
  <div className="v12-buttons"><button className="btn outline" disabled={busy||!draft} onClick={()=>send('counter')}>새 조건으로 역제안</button><button className="btn primary" disabled={busy||!confirmed} onClick={()=>send('accept')}>현재 제안을 시연 수락</button><button className="btn outline" disabled={busy} onClick={()=>send('decline')}>거절</button></div></section>}
  {!mayReply&&thread.status==='UNRESOLVED'&&<p className="v12-tip">현재 상대방의 답변을 기다리는 중입니다. 새 제안이 오면 이곳에서 변경 내용을 비교할 수 있습니다.</p>}
 </>}
 </main>
}
function structured(x:Terms|Record<string,unknown>|undefined,template:Terms):Terms{return x?.schema_version===2?JSON.parse(JSON.stringify(x)) as Terms:JSON.parse(JSON.stringify(template)) as Terms}
export function TermsEditor({terms,onChange,availableAssets}:{terms:Terms;onChange:(t:Terms)=>void;availableAssets?:string[]}){
 function edit<K extends keyof Terms>(k:K,v:Terms[K]){onChange({...terms,[k]:v})}
 function supportEdit<K extends keyof Support>(k:K,v:Support[K]){edit('support',{...terms.support,[k]:v})}
 return <div className="v12-fields"><label>금액 (원)<input className="input" type="number" min="1" max="1000000000" value={terms.price_krw} onChange={e=>edit('price_krw',Number(e.target.value))}/></label>
 <label>권리 범위<select className="input select" value={terms.rights_type} onChange={e=>edit('rights_type',e.target.value)}>{Object.entries(rights).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select></label>
 <label>인계 기간 (일)<input className="input" type="number" min="0" max="365" value={terms.handover_days} onChange={e=>edit('handover_days',Number(e.target.value))}/></label>
 <label>지원 기간 (판매자 동의 필요)<select className="input select" value={terms.support.days} onChange={e=>{const days=Number(e.target.value);edit('support',{...terms.support,days,included_case_limit:daysMap[days],scope_codes:days?['SETUP_GUIDANCE','EXISTING_FUNCTION_GUIDANCE']:[]})}}>{[0,7,14,30].map(n=><option key={n} value={n}>{n?n+'일 · 기본 '+daysMap[n]+'건':'지원 없음'}</option>)}</select></label>
 {terms.support.days>0&&<><label>지원 문의 건수<input className="input" type="number" min="1" max="30" value={terms.support.included_case_limit} onChange={e=>supportEdit('included_case_limit',Number(e.target.value))}/></label><label>답변 권장 시간<input className="input" type="number" min="24" max="336" value={terms.support.reply_goal_hours} onChange={e=>supportEdit('reply_goal_hours',Number(e.target.value))}/></label><fieldset><legend>지원 범위</legend>{Object.entries(scopeLabels).map(([key,label])=><label key={key} className="v12-check"><input type="checkbox" checked={terms.support.scope_codes.includes(key)} onChange={e=>supportEdit('scope_codes',e.target.checked?[...terms.support.scope_codes,key]:terms.support.scope_codes.filter(s=>s!==key))}/>{label}</label>)}</fieldset></>}
 <label className="v12-span">제공 자산 선택 (원래 매물에서 제공 가능한 자산)<div className="v12-asset-list">{[...(availableAssets||terms.included_assets),...terms.excluded_assets.filter(x=>!(availableAssets||terms.included_assets).includes(x))].map(a=><label key={a} className="v12-check"><input type="checkbox" checked={terms.included_assets.includes(a)} disabled={terms.excluded_assets.includes(a)} onChange={e=>edit('included_assets',e.target.checked?[...terms.included_assets,a]:terms.included_assets.filter(x=>x!==a))}/>{a}{terms.excluded_assets.includes(a)?' · 제외 약정':''}</label>)}</div></label>
 <label className="v12-span">별도 조건 메모<textarea className="input textarea" rows={3} maxLength={1500} value={terms.buyer_conditions_note} onChange={e=>edit('buyer_conditions_note',e.target.value)}/></label>
 <label className="v12-span">지원 제외 사항<textarea className="input textarea" rows={2} maxLength={600} value={terms.support.exceptions_note} onChange={e=>supportEdit('exceptions_note',e.target.value)}/></label></div>
}

type Policy={available:boolean;days:number;case_limit:number;used_cases:number;remaining_cases:number;scope_codes:string[];starts_at:string|null;ends_at:string|null;legacy_terms_unverified?:boolean};
type Case={id:string;transaction_id:string;roadmap_task_id:string|null;title:string;category:string;coverage_type:string;status:string;description:string;version:number;opened_at:string};
type Message={id:string;sender_id:string;body:string;message_type:string;created_at:string};
const catLabels:Record<string,string>={...scopeLabels,MISSING_ASSET:'약정된 자료 누락',RIGHTS_CONCERN:'권리 관련 문제',OUT_OF_SCOPE:'추가 개발·별도 협의'};
const coverLabels:Record<string,string>={IN_SCOPE:'약정 내 기술 지원',HANDOVER_REMEDY:'인수 의무·권리 보완',OUT_OF_SCOPE:'별도 협의',UNDER_REVIEW:'범위 검토 중'};
const statusLabels:Record<string,string>={OPEN:'접수',NEEDS_INFO:'추가 확인',SELLER_REPLIED:'판매자 답변',BUYER_REVIEW:'구매자 확인',RESOLVED:'해결 완료',ESCALATED:'관리자 검토',CLOSED_UNRESOLVED:'미해결 종결'};
export function SupportCenter({transactionId,buyer,eligible,selectedTaskId}:{transactionId:string;buyer:boolean;eligible:boolean;selectedTaskId:string}){
 const [policy,setPolicy]=useState<Policy|null>(null),[cases,setCases]=useState<Case[]>([]),[tasks,setTasks]=useState<{id:string;title:string}[]>([]);
 const [chosen,setChosen]=useState(''),[detail,setDetail]=useState<{case:Case;messages:Message[]}|null>(null);
 const [category,setCategory]=useState('SETUP_GUIDANCE'),[task,setTask]=useState(''),[title,setTitle]=useState(''),[description,setDescription]=useState(''),[reply,setReply]=useState('');
 const [busy,setBusy]=useState(false),[err,setErr]=useState(''),[msg,setMsg]=useState('');
 const refresh=useCallback(async()=>{const [p,c]=await Promise.all([api<Policy>(`/transactions/${transactionId}/support-policy`),api<{items:Case[]}>(`/transactions/${transactionId}/support-cases`)]);setPolicy(p);setCases(c.items)},[transactionId]);
 useEffect(()=>{refresh().catch(e=>setErr(errorText(e)));if(buyer&&eligible){api<{tasks?:{id:string;title:string}[]}>(`/transactions/${transactionId}/development-roadmap`).then(v=>setTasks(v.tasks||[])).catch(()=>{})}},[refresh,eligible,buyer,transactionId]);
 useEffect(()=>{if(selectedTaskId){setTask(selectedTaskId);document.getElementById('workspace-support')?.scrollIntoView({behavior:'smooth'})}},[selectedTaskId]);
 useEffect(()=>{if(chosen)api<{case:Case;messages:Message[]}>(`/transactions/${transactionId}/support-cases/${chosen}`).then(setDetail).catch(e=>setErr(errorText(e)))},[chosen,cases]);
 async function perform(fn:()=>Promise<unknown>){setBusy(true);setErr('');setMsg('');try{await fn();await refresh();setMsg('요청 내용이 저장됐습니다.')}catch(e){setErr(errorText(e));if((e as {status?:number}).status===409)await refresh().catch(()=>{})}finally{setBusy(false)}}
 const expired=!!policy?.ends_at&&Date.now()>new Date(policy.ends_at).getTime();const normalAllowed=eligible&&!!policy?.remaining_cases&&!expired;
 const selectable=Object.keys(catLabels);const limited=!['MISSING_ASSET','RIGHTS_CONCERN','OUT_OF_SCOPE'].includes(category);
 const selected=detail?.case;
 return <section id="workspace-support" className="deal-section v12-support"><div className="deal-header"><div><p className="eyebrow">AFTER HANDOVER</p><h2>판매자 지원 센터</h2></div><span className="deal-demo">시연 지원</span></div>
 <p className="deal-muted">판매자가 약속한 범위에서만 기술 질문을 접수합니다. 자료 누락·권리 문제는 일반 기술 지원 건수에서 차감되지 않습니다.</p>
 {policy&&<div className="v12-stats"><div><small>합의 지원 기간</small><strong>{policy.days}일</strong></div><div><small>남은 기술 문의</small><strong>{policy.remaining_cases}/{policy.case_limit}건</strong></div><div><small>지원 기한</small><strong>{policy.ends_at?fmt(policy.ends_at):'인수 완료 후 시작'}</strong></div></div>}
 {policy?.legacy_terms_unverified&&<p className="v12-warning">이전 자유 형식 합의에는 검증된 지원 약정이 없어 일반 기술 문의를 자동 제공하지 않습니다. 인계 자료 누락이나 권리 문제는 접수할 수 있습니다.</p>}
 {err&&<p role="alert" className="v12-error">{err}</p>}{msg&&<p role="status" className="v12-success">{msg}</p>}
 {buyer&&eligible&&<form className="v12-edit" onSubmit={e=>{e.preventDefault();perform(async()=>{await api(`/transactions/${transactionId}/support-cases`,body({category,title,description,roadmap_task_id:task||null,attachment_refs:[]}));setTitle('');setDescription('')})}}><h3>지원 요청하기</h3>
 <label>문의 종류<select className="input select" value={category} onChange={e=>setCategory(e.target.value)}>{selectable.map(k=><option key={k} value={k}>{catLabels[k]}{policy?.scope_codes.includes(k)?' · 약정 내':' '}</option>)}</select></label>
 <label>연결할 개발 작업 (선택)<select className="input select" value={task} onChange={e=>setTask(e.target.value)}><option value="">연결 안 함</option>{tasks.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>
 <label>제목<input className="input" required minLength={5} maxLength={150} value={title} onChange={e=>setTitle(e.target.value)}/></label>
 <label>어떤 어려움이 있나요?<textarea className="input textarea" rows={3} required minLength={10} maxLength={4000} value={description} onChange={e=>setDescription(e.target.value)} placeholder="비밀번호·API 키를 제외하고 상황과 오류를 설명해 주세요."/></label>
 {limited&&!normalAllowed&&<p className="v12-warning">이 유형은 약정 기간·범위·건수 제한을 받습니다. 기간이나 범위를 초과했다면 ‘추가 개발·별도 협의’를 선택하세요.</p>}
 <button className="btn primary" disabled={busy||(limited&&(!normalAllowed||!policy?.scope_codes.includes(category)))}>지원 요청 접수</button></form>}
 {!eligible&&<p className="v12-tip">구매자의 시연 인수 확인이 완료되면 지원 기간이 시작됩니다.</p>}
 <div className="v12-case-grid"><div><h3>지원 요청 {cases.length}건</h3>{!cases.length&&<p>아직 접수된 요청이 없습니다.</p>}{cases.map(c=><button key={c.id} type="button" className={'v12-case-item '+(chosen===c.id?'active':'')} onClick={()=>setChosen(c.id)}><strong>{c.title}</strong><small>{coverLabels[c.coverage_type]} · {statusLabels[c.status]}</small><span>{fmt(c.opened_at)}</span></button>)}</div>
 {detail&&<article className="v12-case-detail"><h3>{detail.case.title}</h3><p>{coverLabels[detail.case.coverage_type]} · {statusLabels[detail.case.status]}</p><div className="v12-conversation">{detail.messages.map(m=><div key={m.id}><small>{fmt(m.created_at)} · {m.message_type}</small><p>{m.body}</p></div>)}</div>{!['RESOLVED','CLOSED_UNRESOLVED'].includes(detail.case.status)&&<>
 <label>새 답변<textarea className="input textarea" rows={3} maxLength={4000} value={reply} onChange={e=>setReply(e.target.value)}/></label>
 <div className="v12-buttons"><button className="btn outline" disabled={busy||reply.trim().length<2} onClick={()=>perform(async()=>{await api(`/transactions/${transactionId}/support-cases/${detail.case.id}/messages`,body({body:reply,expected_version:detail.case.version,attachment_refs:[]}));setReply('')})}>답변 보내기</button>
 {buyer&&<button className="btn primary" disabled={busy} onClick={()=>perform(()=>api(`/transactions/${transactionId}/support-cases/${detail.case.id}/resolve`,body({expected_version:detail.case.version})))}>해결 완료 확인</button>}
 <button className="btn outline" disabled={busy||reply.trim().length<2} onClick={()=>perform(()=>api(`/transactions/${transactionId}/support-cases/${detail.case.id}/escalate`,body({body:reply,expected_version:detail.case.version,attachment_refs:[]})))}>관리자 검토 요청</button></div>
 {!buyer&&detail.case.coverage_type!=='HANDOVER_REMEDY'&&<div className="v12-buttons"><button className="btn outline" disabled={busy||reply.trim().length<10} onClick={()=>perform(()=>api(`/transactions/${transactionId}/support-cases/${detail.case.id}/coverage`,body({coverage_type:'OUT_OF_SCOPE',reason:reply,expected_version:detail.case.version})))}>사유를 남기고 별도 협의로 분류</button></div>}
 </>}</article>}</div></section>
}

export function ProjectWorkspaceOverview({transactionId}:{transactionId:string}){
 const [data,setData]=useState<{listing_title:string;next_action:string;support:Policy;status:string}|null>(null);
 useEffect(()=>{api<typeof data>(`/transactions/${transactionId}/workspace`).then(setData).catch(()=>{})},[transactionId]);
 return <div className="v12-project-overview"><div><small>인수 프로젝트</small><h2>{data?.listing_title||'프로젝트 작업실'}</h2><p>다음 단계: {data?.next_action||'거래 조건과 인수 상태를 확인하세요.'}</p></div><nav aria-label="프로젝트 작업실 메뉴"><a href="#workspace-deal">거래·조건</a><a href="#workspace-roadmap">개발 로드맵</a><a href="#workspace-support">판매자 지원</a><a href="#handover-checks">인수 자료</a></nav></div>
}


export function AdminSupportAppeals(){
 const [items,setItems]=useState<Case[]>([]),[chosen,setChosen]=useState('');
 const [detail,setDetail]=useState<{case:Case;messages:Message[]}|null>(null);
 const [note,setNote]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[success,setSuccess]=useState('');
 const refresh=useCallback(async()=>{const r=await api<{items:Case[]}>(`/admin/support-cases`);setItems(r.items)},[]);
 useEffect(()=>{refresh().catch(e=>setError(errorText(e)))},[refresh]);
 useEffect(()=>{if(chosen)api<{case:Case;messages:Message[]}>(`/admin/support-cases/${chosen}`).then(setDetail).catch(e=>setError(errorText(e)))},[chosen]);
 async function decide(action:'REQUEST_INFO'|'CLOSE_UNRESOLVED'){
  if(!detail)return;setBusy(true);setError('');setSuccess('');try{
   await api(`/admin/support-cases/${detail.case.id}/decision`,body({action,note,expected_version:detail.case.version}));
   setNote('');setChosen('');setDetail(null);setSuccess('검토 결과가 저장되고 양측에게 알림을 보냈습니다.');await refresh();
  }catch(e){setError(errorText(e));if((e as {status?:number}).status===409)await refresh().catch(()=>{})}finally{setBusy(false)}
 }
 return <section className="admin-secondary v12-support-admin"><h2>판매자 지원 분쟁 검토 · {items.length}건</h2><p className="deal-muted">시연 거래의 지원 관련 검토 요청입니다. 관리자는 지원 내용을 확인하고 추가 설명을 요청하거나 미해결로 종결합니다. 법적 분쟁 판정이나 권리 이전을 수행하지 않습니다.</p>
 {error&&<p role="alert" className="v12-error">{error}</p>}{success&&<p role="status" className="v12-success">{success}</p>}
 <div className="v12-case-grid"><div>{!items.length?<p>검토 대기 중인 지원 요청이 없습니다.</p>:items.map(c=><button className={'v12-case-item '+(chosen===c.id?'active':'')} key={c.id} onClick={()=>setChosen(c.id)}><strong>{c.title}</strong><small>{catLabels[c.category]||c.category} · {c.id.slice(0,8)}</small></button>)}</div>
 {detail&&<div className="v12-case-detail"><h3>{detail.case.title}</h3><p>{coverLabels[detail.case.coverage_type]}</p><div className="v12-conversation">{detail.messages.map(m=><div key={m.id}><small>{fmt(m.created_at)} · {m.message_type}</small><p>{m.body}</p></div>)}</div><label>검토 의견<textarea className="input textarea" rows={3} minLength={10} maxLength={1000} value={note} onChange={e=>setNote(e.target.value)}/></label><div className="v12-buttons"><button className="btn outline" disabled={busy||note.trim().length<10} onClick={()=>decide('REQUEST_INFO')}>추가 설명 요청</button><button className="btn outline" disabled={busy||note.trim().length<10} onClick={()=>decide('CLOSE_UNRESOLVED')}>미해결 종결</button></div></div>}</div></section>
}
