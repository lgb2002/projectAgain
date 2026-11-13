import {useActionDialog} from './ActionDialog';
import React,{useEffect,useState} from 'react';
import {Link,useNavigate,useSearchParams,useParams} from 'react-router-dom';
import {AlertTriangle,Archive,ArrowLeft,Check,Download,ExternalLink,FileArchive,FileCheck2,KeyRound,LockKeyhole,RefreshCcw,ShieldCheck,Upload,Wallet,Workflow} from 'lucide-react';
import {api,body,errorText,uploadPrivateFile,downloadPrivateFile} from './api';
import {Listing,User,Transaction,money} from './types';
import {InspectionAccess} from './InspectionAccess';

const SCOPE_LABELS:Record<string,string>={
 'listing:read':'프로젝트 정보 조회','listing:draft':'등록 정보 초안 작성','listing:execute':'승인된 프로젝트 수정 실행',
 'buyer_profile:read':'구매 희망 조건 조회','offer:read':'구매 제안 조회','offer:draft':'구매 제안 초안 작성','offer:execute':'승인된 제안 실행',
 'inspection:read':'기술 점검 결과 조회','inspection:write':'기술 점검 보고서 제출','transaction:read':'거래 진행 상태 조회',
 'handover:read':'인수인계 내역 조회','handover:report':'인수 보고서 제출','handover:draft':'인수 작업 초안','handover:execute':'승인된 인수 작업 실행','asset:inspect':'비공개 소스 점검'
};
const SCOPES=['listing:read','listing:draft','listing:execute','buyer_profile:read','offer:read','offer:draft','offer:execute','inspection:read','inspection:write','transaction:read','handover:read','handover:report','handover:draft','handover:execute','asset:inspect'];
type Grant={id:string;scopes:string[];created_at:string;expires_at:string;revoked_at:string|null};
type Asset={id:string;listing_id:string;file_name:string;size_bytes:number;checksum_sha256:string;upload_status:string;malware_scan_status:string;created_at:string};
type Action={id:string;action_type:string;status:string;proposed_payload:Record<string,unknown>;resource_id:string;expires_at:string};
type Report={id:string;listing_id:string;report_type:string;verdict:string;reviewer_kind:string;is_public?:boolean;findings:unknown[];evidence_refs:string[];created_at:string};
type Notice={id:string;kind:string;title:string;read_at:string|null;created_at:string};
type Fix={id:string;description:string;status:string;resolution_note:string|null;created_at:string};
type Share={share_id:string;asset_id:string;file_name:string;size_bytes:number;expires_at:string};
const label=(s:string)=>new Date(s).toLocaleString('ko-KR');
const errText=(e:unknown)=>errorText(e);
function Message({children,type='info'}:{children:React.ReactNode;type?:'info'|'error'|'success'}){return <div className={'op-msg '+type}>{children}</div>}
function Btn({children,onClick,disabled=false,secondary=false}:{children:React.ReactNode;onClick:()=>void;disabled?:boolean;secondary?:boolean}){return <button className={'op-button '+(secondary?'secondary':'')} disabled={disabled} onClick={onClick}>{children}</button>}
function Sect({title,subtitle,children}:{title:string;subtitle?:string;children:React.ReactNode}){return <section className="op-section"><h2>{title}</h2>{subtitle&&<p className="op-sub">{subtitle}</p>}{children}</section>}

export function Operations({user}:{user:User|null}){
 const dialog=useActionDialog();
 const nav=useNavigate();const [params,setParams]=useSearchParams();const tab=params.get('tab')||'files';
 const [list,setList]=useState<Listing[]>([]);const [chosen,setChosen]=useState(params.get('listing')||'');const [assets,setAssets]=useState<Asset[]>([]);
 const [adminAssets,setAdminAssets]=useState<Asset[]>([]);
 const [file,setFile]=useState<File|null>(null);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [msg,setMsg]=useState('');
 const [grants,setGrants]=useState<Grant[]>([]);const [scopes,setScopes]=useState<string[]>(['listing:read','listing:draft','listing:execute','buyer_profile:read','offer:read','offer:draft','inspection:read','inspection:write','transaction:read','handover:read','handover:report','handover:draft','handover:execute']);
 const [token,setToken]=useState('');const [actions,setActions]=useState<Action[]>([]);const [reports,setReports]=useState<Report[]>([]);
 const [notifications,setNotifications]=useState<Notice[]>([]);
 function announce(x:string){setError('');setMsg(x)}
 async function refresh(){if(!user)return;try{
  const [l,g,a,n]=await Promise.all([
   api<Listing[]>('/my/listings'),api<{items:Grant[]}>('/auth/agent-grants'),
   api<{items:Action[]}>('/agent-actions'),api<{items:Notice[]}>('/notifications')]);
  setList(l);setGrants(g.items);setActions(a.items);setNotifications(n.items);
  if(!chosen&&l.length)setChosen(l[0].id);else if(chosen&&l.length&&!l.some(x=>x.id===chosen))setChosen(l[0].id);
  if(user.role==='ADMIN')setAdminAssets((await api<{items:Asset[]}>('/admin/assets')).items);
 }catch(e){setError(errText(e))}}
 async function refreshChosen(){if(!chosen)return;try{
  const [a,r]=await Promise.all([api<{items:Asset[]}>(`/listings/${chosen}/assets`),api<{items:Report[]}>(`/listings/${chosen}/inspection-reports`)]);
  setAssets(a.items);setReports(r.items);
 }catch(e){setAssets([]);setReports([]);setError(errText(e))}}
 useEffect(()=>{refresh()},[user?.id]);useEffect(()=>{refreshChosen()},[chosen]);
 if(!user)return <main className="page-container narrow"><h1>내 업무</h1><Message>먼저 <Link to="/login">로그인</Link>해 주세요.</Message></main>;
 async function doUpload(){if(!chosen||!file)return;setBusy(true);try{const a=await uploadPrivateFile(chosen,file);announce(`${a.file_name} 업로드 완료 · 격리 상태 · 악성코드 검증: ${a.malware_scan_status}`);setFile(null);await refreshChosen();await refresh()}catch(e){setError(errText(e))}finally{setBusy(false)}}
 async function grant(){setBusy(true);try{const g=await api<{token:string}>('/auth/agent-grants',body({scopes,expires_in_hours:12}));setToken(g.token);announce('토큰이 발급됐습니다. 다시 볼 수 없으므로 Streamlit의 환경변수에 안전하게 보관하세요.');await refresh()}catch(e){setError(errText(e))}finally{setBusy(false)}}
 async function mutate(path:string,data:unknown={}){setBusy(true);try{await api(path,body(data));announce('처리됐습니다.');await refresh();await refreshChosen()}catch(e){setError(errText(e))}finally{setBusy(false)}}
 async function download(a:Asset){setBusy(true);try{await downloadPrivateFile(a.id,a.file_name);announce('권한을 확인한 후 파일을 내려받았습니다.')}catch(e){setError(errText(e))}finally{setBusy(false)}}
 const tabs=[['files','비공개 자료'],['inspections','에이전트 실사'],['agent','AI 에이전트 연결'],['approvals','에이전트 승인 요청'],...(user.role==='ADMIN'?[['moderation','관리자 파일 심사']]:[])];
 return <main className="page-container"><div className="page-heading"><Link to="/dashboard" className="back-link"><ArrowLeft size={16}/> 내 프로젝트로</Link><p className="eyebrow">PROJECT MANAGEMENT</p><h1>{tab==='files'?'프로젝트 비공개 자료':tab==='inspections'?'기술 검토 보고서':tab==='agent'?'외부 AI 연결 설정':tab==='approvals'?'AI 작업 승인':'관리자 파일 심사'}</h1><p className="subheading">{tab==='files'?'소스코드와 증빙 자료를 비공개로 안전하게 관리합니다.':tab==='inspections'?'등록된 실사 자료와 공개 범위를 확인합니다.':tab==='agent'?'외부 에이전트가 접근할 수 있는 범위를 설정합니다.':tab==='approvals'?'AI가 제안한 작업을 확인하고 승인 또는 거절합니다.':'관리자 전용 파일 검토 화면입니다.'}</p></div><Message>시연 환경입니다. 대금 결제·소유권 이전·악성파일 안전 인증은 제공하지 않습니다.</Message>
 <nav className="op-tabs">{tabs.map(([k,v])=><button key={k} className={tab===k?'current':''} onClick={()=>{setParams({tab:k});setError('');setMsg('')}}>{v}</button>)}</nav>
 {error&&<Message type="error">{error}</Message>}{msg&&<Message type="success">{msg}</Message>}
 {['files','inspections'].includes(tab)&&<div className="op-pick"><label htmlFor="seller-list">내 프로젝트</label><select id="seller-list" className="input" value={chosen} onChange={e=>setChosen(e.target.value)}><option value="">프로젝트를 선택하세요</option>{list.map(x=><option key={x.id} value={x.id}>{x.title} · {money(x.price_krw)} · {x.status}</option>)}</select><Btn secondary onClick={refreshChosen}>새로고침</Btn></div>}
 {tab==='files'&&<Sect title="프로젝트 원본·증빙 파일" subtitle="ZIP·PDF·MD·TXT·JSON (최대 10MB 기본값). 업로드 후 원본은 비공개 격리되며 관리자 검토가 필요합니다. 외부 코드는 실행하지 않습니다.">
  <div className="op-upload"><label htmlFor="asset-file">첨부 파일 선택</label><input id="asset-file" type="file" accept=".zip,.pdf,.md,.txt,.json" onChange={e=>setFile(e.target.files?.[0]||null)}/><Btn onClick={doUpload} disabled={busy||!file||!chosen}><Upload size={15}/> 비공개 업로드</Btn></div>
  <div className="op-list">{assets.length?assets.map(a=><div className="op-item" key={a.id}><FileArchive size={20}/><div><strong>{a.file_name}</strong><span>{(a.size_bytes/1024).toFixed(1)}KB · {a.upload_status} · 악성코드 검사 {a.malware_scan_status} · SHA-256 {a.checksum_sha256.slice(0,14)}…</span></div>{a.file_name.endsWith('.zip')&&<Btn secondary onClick={()=>mutate(`/assets/${a.id}/static-inspections`)} disabled={busy}><FileCheck2 size={15}/> 정적 검사</Btn>}{a.upload_status==='APPROVED'&&<Btn secondary onClick={()=>download(a)} disabled={busy}><Download size={15}/> 받기</Btn>}</div>):<p className="op-sub">등록된 원본 자료가 없습니다.</p>}</div>
  <Message>공개 매물 페이지에서는 원본 ZIP을 내려받을 수 없습니다. 시연 거래 인수인계 자료 공유는 해당 거래의 판매자가 명시적으로 승인해야 합니다.</Message>
  <InspectionAccess assets={assets} userId={user.id}/>
 </Sect>}
 {tab==='inspections'&&<Sect title="실사 보고서" subtitle="별도 Streamlit 에이전트가 제한된 토큰으로 보고서를 제출합니다. 판매자가 공개하기 전에는 비공개입니다.">
  <div className="op-list">{reports.length?reports.map(r=><div className="op-item" key={r.id}><FileCheck2 size={19}/><div><strong>{r.report_type} · {r.verdict}</strong><span>{r.reviewer_kind} · {label(r.created_at)} · {r.is_public?'공개 승인됨':'비공개'}</span><details><summary>검사 근거 보기</summary><pre className="op-pre">{JSON.stringify(r.findings,null,2)}</pre></details></div><Btn secondary onClick={()=>mutate(`/listings/${chosen}/inspection-reports/${r.id}/visibility`,{is_public:!r.is_public})}>{r.is_public?'비공개로':'보고서 공개'}</Btn></div>):<p className="op-sub">등록된 보고서가 없습니다. 에이전트가 보고서를 실제 제출해야 표시됩니다.</p>}</div>
  <Message>에이전트 검사 결과는 플랫폼 인증이나 전문가 의견이 아닙니다. 공개 시 민감한 내부 정보가 없는지 확인하세요.</Message>
 </Sect>}
 {tab==='agent'&&<Sect title="외부 AI 에이전트 연결" subtitle="Streamlit 앱에서 Python requests로 REST API를 직접 호출합니다. 중간 FastAPI Agent 서버나 Mock Marketplace 서버는 필요하지 않습니다.">
  <div className="op-steps"><p><strong>1</strong> 필요한 접근 권한을 선택합니다.</p><div className="op-scopes">{SCOPES.map(s=><label key={s} title={s}><input type="checkbox" checked={scopes.includes(s)} onChange={e=>setScopes(x=>e.target.checked?[...x,s]:x.filter(v=>v!==s))}/>{SCOPE_LABELS[s]||s}</label>)}</div><p><strong>2</strong> 토큰을 발급하고 Streamlit 환경변수에 저장하세요.</p><Btn onClick={grant} disabled={busy||!scopes.length}><KeyRound size={15}/> 12시간 토큰 발급</Btn>
  {token&&<Message type="success"><strong>이번에 한 번만 공개되는 토큰</strong><textarea className="input" readOnly value={token} rows={3} onClick={e=>(e.target as HTMLTextAreaElement).select()}/><button className="op-button secondary" onClick={()=>navigator.clipboard.writeText(token)}>토큰 복사</button></Message>}
  <p><strong>3</strong> Streamlit에서 <code>MARKETPLACE_API_URL</code>과 <code>MARKETPLACE_API_KEY</code>를 설정합니다. 파일 직접 접근과 실제 거래 처리는 승인 없이 할 수 없습니다.</p></div>
  <h3>발급한 연동 토큰</h3><div className="op-list">{grants.map(g=><div className="op-item" key={g.id}><LockKeyhole size={19}/><div><strong>{g.id.slice(0,8)} · {g.revoked_at?'철회':'유효시간 제한'}</strong><span>{g.scopes.join(' · ')} · 만료 {label(g.expires_at)}</span></div>{!g.revoked_at&&<Btn secondary onClick={()=>mutate(`/auth/agent-grants/${g.id}/revoke`)}>철회</Btn>}</div>)}</div>
 </Sect>}
 {tab==='approvals'&&<Sect title="에이전트 작업 제안 검토" subtitle="에이전트는 제안 초안을 작성하지만 사람이 내용을 확인하고 승인해야 상대방에게 제출할 수 있습니다.">
  {actions.length?actions.map(a=><div className="op-item" key={a.id}><Workflow size={20}/><div><strong>{a.action_type} · {a.status}</strong><span>만료: {label(a.expires_at)} · 대상: {a.resource_id}</span><details><summary>제안 상세 원문 확인</summary><pre className="op-pre">{JSON.stringify(a.proposed_payload,null,2)}</pre></details></div>{a.status==='PENDING_APPROVAL'&&<div className="op-actions"><Btn secondary onClick={()=>mutate(`/agent-actions/${a.id}/reject`)}>거절</Btn><Btn onClick={()=>mutate(`/agent-actions/${a.id}/approve`)}>승인</Btn></div>}{a.status==='APPROVED'&&a.action_type==='SUGGEST_LISTING_UPDATE'&&<Btn onClick={()=>mutate(`/agent-actions/${a.id}/execute`)}>승인한 매물 수정안 반영</Btn>}</div>):<p className="op-sub">현재 승인 대기 작업이 없습니다.</p>}
 </Sect>}
 {tab==='notices'&&<Sect title="거래 알림" subtitle="제안·역제안·파일 검토·인수인계 변경을 확인합니다."><div className="op-list">{notifications.length?notifications.map(n=><div className="op-item" key={n.id}><ShieldCheck size={18}/><div><strong>{n.title}</strong><span>{n.kind} · {label(n.created_at)} · {n.read_at?'읽음':'새 알림'}</span></div>{!n.read_at&&<Btn secondary onClick={()=>mutate(`/notifications/${n.id}/read`)}>읽음</Btn>}</div>):<p className="op-sub">아직 알림이 없습니다.</p>}</div></Sect>}
 {tab==='moderation'&&user.role==='ADMIN'&&<Sect title="비공개 업로드 심사" subtitle="정적 포맷 검사와 악성코드 검사를 혼동하지 마세요. 운영 환경에서는 검사 CLEAN이 아닌 파일을 공개 승인할 수 없습니다.">
  {adminAssets.map(a=><div className="op-item" key={a.id}><Archive size={20}/><div><strong>{a.file_name}</strong><span>{a.upload_status} · 악성코드 검사 {a.malware_scan_status} · {a.checksum_sha256.slice(0,14)}…</span></div>{a.upload_status==='QUARANTINED'&&<div className="op-actions"><Btn secondary onClick={async()=>{const reason=await dialog.ask({title:'업로드 거부 사유',minimum:5,danger:true,confirmText:'거부 처리'});if(reason)mutate(`/admin/assets/${a.id}/review`,{status:'REJECTED',reason})}}>거부</Btn><Btn onClick={async()=>{const reason=await dialog.ask({title:'비공개 파일 승인 근거',description:'운영 환경에서 악성코드 검사 합격 여부를 확인한 경우에만 승인하세요.',minimum:5,confirmText:'승인 처리'});if(reason)mutate(`/admin/assets/${a.id}/review`,{status:'APPROVED',reason})}}>검토 승인</Btn></div>}</div>)}
 </Sect>}
 {dialog.dialog}</main>
}

export function TransferTools({transactionId,seller}:{transactionId:string;seller:boolean}){
 const dialog=useActionDialog();
 const [assets,setAssets]=useState<Asset[]>([]);const [shares,setShares]=useState<Share[]>([]);const [fixes,setFixes]=useState<Fix[]>([]);
 const [desc,setDesc]=useState('');const [msg,setMsg]=useState('');const [listingId,setListingId]=useState('');const [err,setErr]=useState('');
 async function refresh(){try{const [tx,shared,fix]=await Promise.all([
   api<Transaction>(`/transactions/${transactionId}`),api<{items:Share[]}>(`/transactions/${transactionId}/shared-assets`),
   api<{items:Fix[]}>(`/transactions/${transactionId}/fix-requests`)]);
  setShares(shared.items);setFixes(fix.items);setListingId(tx.listing_id);
  if(seller){const a=await api<{items:Asset[]}>(`/listings/${tx.listing_id}/assets`);setAssets(a.items.filter(x=>x.upload_status==='APPROVED'))}
 }catch(e){setErr(errText(e))}}
 useEffect(()=>{refresh()},[transactionId]);
 async function apply(path:string,data:unknown){try{await api(path,body(data));setErr('');setMsg('반영됐습니다.');await refresh()}catch(e){setErr(errText(e))}}
 async function retrieve(s:Share){try{await downloadPrivateFile(s.asset_id,s.file_name);setMsg('자료를 다운로드했습니다.')}catch(e){setErr(errText(e))}}
 return <section className="op-section"><h2>인수인계 증빙·보완 요청</h2><p className="op-sub">시연용 접근 공유입니다. 실제 금전 지급·소유권 이전과는 관계없습니다.</p>
  {err&&<Message type="error">{err}</Message>}{msg&&<Message type="success">{msg}</Message>}
  {seller&&<div className="op-list"><h3>구매자에게 자료 공유</h3>{assets.length?assets.map(a=><div className="op-item" key={a.id}><FileArchive/><div><strong>{a.file_name}</strong><span>검토됨 · {a.checksum_sha256.slice(0,14)}…</span></div><Btn secondary onClick={()=>apply(`/assets/${a.id}/shares`,{transaction_id:transactionId,expires_in_hours:12})}>12시간 공유</Btn></div>):<p className="op-sub">공유 가능한 파일이 없습니다. <Link to="/operations?tab=files">업무실에서 파일을 등록</Link>하세요.</p>}</div>}
  <div className="op-list"><h3>공유된 자료</h3>{shares.length?shares.map(s=><div className="op-item" key={s.share_id}><Download size={18}/><div><strong>{s.file_name}</strong><span>{label(s.expires_at)}까지 · {(s.size_bytes/1024).toFixed(1)}KB</span></div><Btn secondary onClick={()=>retrieve(s)}>다운로드</Btn>{seller&&<Btn secondary onClick={()=>apply(`/assets/shares/${s.share_id}/revoke`,{})}>공유 철회</Btn>}</div>):<p className="op-sub">아직 공유된 파일이 없습니다.</p>}</div>
  {!seller&&<div className="op-upload"><label>판매자에게 보완 요청</label><textarea className="input" rows={3} value={desc} onChange={e=>setDesc(e.target.value)} placeholder="어떤 파일이나 환경 설정이 부족한지 구체적으로 적어주세요."/><Btn disabled={desc.trim().length<10} onClick={async()=>{await apply(`/transactions/${transactionId}/fix-requests`,{description:desc});setDesc('')}}>보완 요청 등록</Btn></div>}
  <div className="op-list"><h3>보완 요청 이력</h3>{fixes.length?fixes.map(f=><div className="op-item" key={f.id}><AlertTriangle size={19}/><div><strong>{f.description}</strong><span>{f.status} · {f.resolution_note||'응답 대기'} · {label(f.created_at)}</span></div>{seller&&f.status==='OPEN'&&<div className="op-actions"><Btn secondary onClick={async()=>{const r=await dialog.ask({title:'보완 요청 거절 사유',minimum:3,confirmText:'답변 제출'});if(r)apply(`/transactions/${transactionId}/fix-requests/${f.id}/resolve`,{status:'DECLINED',resolution_note:r})}}>거절</Btn><Btn onClick={async()=>{const r=await dialog.ask({title:'보완 처리 완료 내용',minimum:3,confirmText:'완료 기록'});if(r)apply(`/transactions/${transactionId}/fix-requests/${f.id}/resolve`,{status:'RESOLVED',resolution_note:r})}}>처리 완료</Btn></div>}{!seller&&f.status==='RESOLVED'&&<div className="op-actions"><Btn secondary onClick={()=>apply(`/transactions/${transactionId}/fix-requests/${f.id}/reopen`,{})}>다시 보완 요청</Btn><Btn onClick={()=>apply(`/transactions/${transactionId}/fix-requests/${f.id}/confirm`,{})}>보완 완료 확인</Btn></div>}{!seller&&f.status==='DECLINED'&&<Btn secondary onClick={()=>apply(`/transactions/${transactionId}/fix-requests/${f.id}/reopen`,{})}>다시 보완 요청</Btn>}</div>):<p className="op-sub">등록된 보완 요청이 없습니다.</p>}</div>
 {dialog.dialog}</section>
}

export function ResetPassword(){const [params]=useSearchParams();const [email,setEmail]=useState('');const [password,setPassword]=useState('');const [msg,setMsg]=useState('');const [dev,setDev]=useState('');const [err,setErr]=useState('');const token=params.get('token');
 async function go(){try{const res=token?await api<{message:string}>('/auth/confirm-password-reset',body({token,new_password:password})):await api<{message:string;development_reset_token?:string}>('/auth/request-password-reset',body({email}));setMsg(res.message);setDev('development_reset_token' in res && typeof res.development_reset_token === 'string' ? res.development_reset_token : '');setErr('')}catch(e){setErr(errText(e))}}
 return <main className="page-container narrow"><div className="page-heading"><p className="eyebrow">ACCOUNT SECURITY</p><h1>비밀번호 재설정</h1><p className="subheading">계정 재설정에는 이메일 인증이 필요합니다.</p></div>{err&&<Message type="error">{err}</Message>}{msg&&<Message type="success">{msg}</Message>}
  {token?<div className="op-upload"><label>새 비밀번호 (12자 이상)</label><input className="input" type="password" value={password} onChange={e=>setPassword(e.target.value)}/><Btn onClick={go} disabled={password.length<12}>비밀번호 변경</Btn></div>:<div className="op-upload"><label>가입한 이메일</label><input className="input" type="email" value={email} onChange={e=>setEmail(e.target.value)}/><Btn onClick={go} disabled={!email.includes('@')}>재설정 안내 요청</Btn></div>}
  {dev&&<Message>로컬 개발용 토큰 (실서비스에는 표시되지 않음): <Link to={'/reset-password?token='+dev}>재설정 화면 열기</Link></Message>}
 </main>
}
