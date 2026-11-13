import React,{useCallback,useEffect,useMemo,useState} from 'react';
import {AlertCircle,ArrowRight,CheckCircle2,ClipboardList,Download,HelpCircle,LockKeyhole,Plus,RefreshCcw} from 'lucide-react';
import {api,body,patch,errorText} from './api';

type Phase={key:string;label:string;description:string};
type Difficulty='EASY'|'MEDIUM'|'HARD';
type Assistance='SELF'|'GUIDED'|'EXPERT';
type Status='NOT_STARTED'|'IN_PROGRESS'|'BLOCKED'|'COMPLETED';
type Task={id?:string;key:string;phase:string;title:string;detail:string;difficulty:Difficulty;
  assistance:Assistance;priority:'LOW'|'MEDIUM'|'HIGH';prerequisites:string[];waiting_on?:string[];
  steps:string[];success_criteria:string[];evidence:string;source_kind:string;position:number;
  status?:Status;buyer_note?:string;blocked_reason?:string|null;support_case_ids?:string[];version?:number;
  personalized_guidance?:{skill_level:string;guidance_level:string;intro:string;preparation:string;checklist:string[];completion_checks:string[];help_guidance:string;waiting_on_titles:string[];blocked_help:string|null;objective_note:string}};
type Preview={title:string;analysis_basis:string;phases:Phase[];tasks:Task[];disclaimer:string};
type Plan={created:boolean;id?:string;transaction_id:string;phases?:Phase[];tasks?:Task[];
  completed_tasks?:number;total_tasks?:number;progress_percent?:number;source_changed_since_creation?:boolean;
  buyer_context?:{skill_level:string;objective:string;preferred_guidance_level:string;version:number};
  analysis_basis?:string;preview?:{phase_definitions:Phase[];tasks:Task[];disclaimer:string};disclaimer?:string};
const assistanceLabels:Record<Assistance,string>={SELF:'혼자 진행 가능',GUIDED:'도움받아 진행 권장',EXPERT:'전문가 검토 권장'};
const difficultyLabels:Record<Difficulty,string>={EASY:'쉬움',MEDIUM:'보통',HARD:'어려움'};
const statusLabels:Record<Status,string>={NOT_STARTED:'시작 전',IN_PROGRESS:'진행 중',BLOCKED:'막힘',COMPLETED:'완료'};
const evidenceLabels:Record<string,string>={GENERAL_GUIDANCE:'일반 점검 권고',SELLER_DECLARATION:'판매자 제공 정보',SELLER_OR_STATIC_SIGNAL:'판매자·정적 파일 단서',STATIC_FOUND:'관련 파일 발견',STATIC_NOT_FOUND:'관련 파일 미탐지',STATIC_SIGNAL:'정적 분석 단서',NOT_RUNTIME_VERIFIED:'실행 미검증',BUYER_ADDED:'직접 추가한 작업'};
const assistanceReasons:Record<Assistance,string>={
 SELF:'개발 도구를 사용하지 않고도 확인할 수 있도록 작업을 나눴습니다. 어려우면 판매자에게 도움을 요청하세요.',
 GUIDED:'설치·설정이나 테스트 경험이 필요할 수 있습니다. 안내를 참고하고 막히는 지점은 개발 경험이 있는 사람과 확인하세요.',
 EXPERT:'권리, 데이터, 보안 또는 복잡한 기술 판단이 포함될 수 있습니다. 전문성을 가진 사람의 검토를 권장합니다.'
};
const isBlocked=(task:Task)=>!!task.waiting_on?.length;

export function RoadmapPreview({listingId,includeDemo}:{listingId:string;includeDemo:boolean}){
 const [data,setData]=useState<Preview|null>(null),[open,setOpen]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let alive=true;api<Preview>(`/listings/${listingId}/development-roadmap-preview${includeDemo?'?include_demo=true':''}`)
  .then(x=>{if(alive)setData(x)}).catch(e=>{if(alive)setError(errorText(e))});return()=>{alive=false}},[listingId,includeDemo]);
 if(!data)return error?<section className="detail-section roadmap-preview"><h2>인수 후 개발 로드맵</h2><p className="roadmap-muted">예상 작업을 불러오지 못했습니다.</p></section>:null;
 const expertCount=data.tasks.filter(t=>t.assistance==='EXPERT').length;
 return <section className="detail-section roadmap-preview" aria-label="인수 후 개발 로드맵 예상">
  <div className="roadmap-section-header"><div><p className="roadmap-eyebrow">AFTER TAKEOVER</p><h2><ClipboardList size={21}/> 인수 후 개발 로드맵</h2></div><span className="roadmap-preview-badge">예상 작업</span></div>
  <p className="roadmap-intro">이 프로젝트를 이어받은 뒤 어떤 일을 어떤 순서로 해야 할지 살펴보세요. 개발 경험이 적은 분을 위한 일반적인 도움 수준도 표시합니다.</p>
  <div className="roadmap-stats"><div><strong>{data.tasks.length}</strong><span>예상 작업</span></div><div><strong>{data.phases.length}</strong><span>진행 단계</span></div><div><strong>{expertCount}</strong><span>전문가 검토 권장</span></div></div>
  <div className="roadmap-preview-phases">{data.phases.map(p=><div key={p.key} className="roadmap-preview-phase"><span>{p.label}</span><strong>{data.tasks.filter(t=>t.phase===p.key).length}개</strong></div>)}</div>
  {open&&<div className="roadmap-preview-tasks">{data.phases.map(p=><div key={p.key}><h3>{p.label}</h3>{data.tasks.filter(t=>t.phase===p.key).map(t=><div className="roadmap-mini-task" key={t.key}><strong>{t.title}</strong><span>{difficultyLabels[t.difficulty]} · {assistanceLabels[t.assistance]}</span><p>{t.detail}</p>{t.prerequisites.length>0&&<small>선행 작업: {t.prerequisites.map(k=>data.tasks.find(x=>x.key===k)?.title||k).join(' → ')}</small>}</div>)}</div>)}</div>}
  <button className="roadmap-toggle" onClick={()=>setOpen(!open)}>{open?'예상 작업 접기':'전체 작업 및 선행 조건 보기'} <ArrowRight size={16}/></button>
  <p className="roadmap-disclaimer"><AlertCircle size={15}/>{data.analysis_basis==='SELLER_DECLARATION_ONLY'?'소스 분석 없이 판매자가 입력한 매물 정보로 작성했습니다. ':'기존 정적 분석 및 판매자 정보를 바탕으로 작성했습니다. '}{data.disclaimer}</p>
 </section>
}

export function RoadmapWorkspace({transactionId,eligible,onSupportRequest}:{transactionId:string;eligible:boolean;onSupportRequest?:(taskId:string)=>void}){
 const [plan,setPlan]=useState<Plan|null>(null),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[err,setErr]=useState(''),[msg,setMsg]=useState('');
 const [notes,setNotes]=useState<Record<string,string>>({});
 const [blockReasons,setBlockReasons]=useState<Record<string,string>>({});
 const [level,setLevel]=useState('BASIC'),[guidance,setGuidance]=useState('DETAILED'),[objective,setObjective]=useState('');
 const [adding,setAdding]=useState(false),[title,setTitle]=useState(''),[detail,setDetail]=useState('');
 const [phase,setPhase]=useState('VERIFY'),[difficulty,setDifficulty]=useState<Difficulty>('MEDIUM');
 const [assistance,setAssistance]=useState<Assistance>('GUIDED'),[prerequisite,setPrerequisite]=useState('');
 const [openTask,setOpenTask]=useState<string|null>(null);
 const refresh=useCallback(async()=>{if(!eligible)return;setLoading(true);try{const x=await api<Plan>(`/transactions/${transactionId}/development-roadmap`);setPlan(x);if(x.buyer_context){setLevel(x.buyer_context.skill_level);setGuidance(x.buyer_context.preferred_guidance_level);setObjective(x.buyer_context.objective)}setErr('')}catch(e){setErr(errorText(e))}finally{setLoading(false)}},[transactionId,eligible]);
 useEffect(()=>{refresh()},[refresh]);
 const tasks=useMemo(()=>plan?.tasks||[],[plan?.tasks]);
 async function create(){setBusy(true);setErr('');try{setPlan(await api<Plan>(`/transactions/${transactionId}/development-roadmap`,body({})));setMsg('내 로드맵이 생성됐습니다. 작업 완료 내역은 별도로 저장됩니다.')}catch(e){setErr(errorText(e))}finally{setBusy(false)}}
 async function progress(t:Task,status:Status){if(!t.id)return;setBusy(true);setErr('');setMsg('');try{
   const updated=await api<Plan>(`/transactions/${transactionId}/development-roadmap/tasks/${t.id}`,patch({status,buyer_note:notes[t.id]??t.buyer_note??'',blocked_reason:status==='BLOCKED'?(blockReasons[t.id]||t.blocked_reason||'OTHER'):null,expected_version:t.version}));setPlan(updated);
   setMsg('작업 상태를 저장했습니다.');
  }catch(e){setErr(errorText(e));if((e as any)?.status===409)await refresh()}finally{setBusy(false)}}
 async function add(e:React.FormEvent){e.preventDefault();setBusy(true);setErr('');setMsg('');try{
   const result=await api<Plan>(`/transactions/${transactionId}/development-roadmap/tasks`,body({title,detail,phase,difficulty,assistance,priority:'MEDIUM',prerequisites:prerequisite?[prerequisite]:[]}));
   setPlan(result);setAdding(false);setTitle('');setDetail('');setPrerequisite('');setMsg('개인 작업이 추가됐습니다.');
  }catch(e){setErr(errorText(e))}finally{setBusy(false)}}
 if(!eligible)return <section className="roadmap-workspace roadmap-locked"><div className="roadmap-section-header"><div><p className="roadmap-eyebrow">YOUR NEXT STEPS</p><h2><LockKeyhole size={21}/> 인수 후 개발 로드맵</h2></div></div><p>모의 인수인계가 완료되면 구매자가 자신의 로드맵을 생성하고 진행 상황을 기록할 수 있습니다. 실제 매매나 권리 이전이 완료됐다는 뜻은 아닙니다.</p></section>;
 return <section className="roadmap-workspace" aria-label="구매자 인수 후 개발 로드맵">
  <div className="roadmap-section-header"><div><p className="roadmap-eyebrow">YOUR NEXT STEPS</p><h2><ClipboardList size={22}/> 인수 후 개발 로드맵</h2></div>{plan?.created&&<a className="roadmap-download" href={`/api/v1/transactions/${transactionId}/development-roadmap/export`}><Download size={15}/> Markdown 저장</a>}</div>
  <p className="roadmap-intro">인수한 프로젝트를 직접 이어가기 위한 순서표입니다. 선행 작업부터 마치고, 어려운 단계는 전문가 도움을 검토하세요.</p>
  <p className="roadmap-disclaimer"><AlertCircle size={15}/>현재 거래는 DEMO이며 실제 결제·법적 권리 이전은 이루어지지 않았습니다. 개발 기간이나 정상 운영을 보장하지 않습니다.</p>
  {loading&&<p className="roadmap-muted">로드맵을 확인하고 있습니다…</p>}
  {err&&<p role="alert" className="roadmap-error">{err}</p>}{msg&&<p role="status" className="roadmap-success">{msg}</p>}
  {!loading&&plan&&!plan.created&&<div className="roadmap-create"><h3>나만의 진행표 만들기</h3><p>매물 정보와 정적 분석 결과를 바탕으로 기본 작업 {(plan.preview?.tasks||[]).length}개를 생성합니다. 이후 작업 상태와 메모를 독립적으로 기록할 수 있습니다.</p><button className="btn primary" onClick={create} disabled={busy}>{busy?'생성 중…':'내 개발 로드맵 만들기'} <ArrowRight size={16}/></button><p className="roadmap-muted">생성 후 원본 매물 정보가 바뀌더라도 기존 내 진행 기록은 자동으로 덮어쓰지 않습니다.</p></div>}
  {plan?.created&&<>
   <div className="v12-edit"><h3>내 개발 수준과 안내 방식</h3><div className="v12-fields"><label>개발 경험<select className="input select" value={level} onChange={e=>setLevel(e.target.value)}><option value="NONE">개발 경험 없음</option><option value="BASIC">기초 경험</option><option value="INTERMEDIATE">중급</option><option value="ADVANCED">상급</option></select></label><label>안내 수준<select className="input select" value={guidance} onChange={e=>setGuidance(e.target.value)}><option value="DETAILED">자세한 단계별 안내</option><option value="STANDARD">기본 안내</option><option value="BRIEF">간단한 체크리스트</option></select></label><label className="v12-span">내 목표<input className="input" maxLength={500} value={objective} onChange={e=>setObjective(e.target.value)} placeholder="예: 서비스를 직접 운영해 보기"/></label></div><button className="btn outline" disabled={busy} onClick={async()=>{setBusy(true);setErr('');try{await api(`/transactions/${transactionId}/roadmap/buyer-context`,patch({skill_level:level,objective,preferred_guidance_level:guidance,expected_version:plan.buyer_context?.version||1}));await refresh();setMsg('프로젝트별 안내 설정이 저장됐습니다. 기존 작업 진행 상황은 유지됩니다.')}catch(e){setErr(errorText(e))}finally{setBusy(false)}}}>나에게 맞는 안내 설정 저장</button></div>
   {plan.source_changed_since_creation&&<p className="roadmap-warning"><AlertCircle size={16}/>매물이나 기술 분석 정보가 로드맵 생성 이후 변경됐습니다. 기존 작업 기록은 보존됩니다. 변경 사항은 직접 확인하세요.</p>}
   <div className="roadmap-progress"><div className="roadmap-progress-title"><strong>전체 진행률</strong><span>{plan.completed_tasks}/{plan.total_tasks}개 완료 · {plan.progress_percent}%</span></div><div className="roadmap-progress-track"><div style={{width:`${plan.progress_percent||0}%`}}/></div></div>
   {(plan.phases||[]).map(p=><div className="roadmap-phase" key={p.key}><div className="roadmap-phase-heading"><div><h3>{p.label}</h3><p>{p.description}</p></div><span>{tasks.filter(t=>t.phase===p.key&&t.status==='COMPLETED').length}/{tasks.filter(t=>t.phase===p.key).length} 완료</span></div>
    {tasks.filter(t=>t.phase===p.key).map(t=><article key={t.key} className={'roadmap-task'+(t.status==='COMPLETED'?' is-complete':'')}>
      <div className="roadmap-task-top"><button type="button" className="roadmap-task-expand" onClick={()=>setOpenTask(openTask===t.key?null:t.key)} aria-expanded={openTask===t.key}>
        <span className="roadmap-task-indicator">{t.status==='COMPLETED'?<CheckCircle2 size={18}/>:<span>{t.position}</span>}</span>
        <span><strong>{t.title}</strong><small>{difficultyLabels[t.difficulty]} · {assistanceLabels[t.assistance]} · {evidenceLabels[t.evidence]||'참고 정보'}</small></span></button>
       <span className={'roadmap-status-tag status-'+(t.status||'NOT_STARTED').toLowerCase()}>{statusLabels[t.status||'NOT_STARTED']}</span></div>
      {!!t.waiting_on?.length&&<p className="roadmap-dependency"><LockKeyhole size={13}/> 선행 작업 대기: {t.waiting_on.map(k=>tasks.find(a=>a.key===k)?.title||k).join(', ')}</p>}
      {openTask===t.key&&<div className="roadmap-task-details"><p>{t.detail}</p><div className="roadmap-assist-note"><HelpCircle size={16}/><span>{assistanceReasons[t.assistance]}</span></div>
        {!!t.steps.length&&<div><strong>어떻게 진행하나요?</strong><ol>{t.steps.map((s,i)=><li key={i}>{s}</li>)}</ol></div>}
        {!!t.success_criteria.length&&<div><strong>완료 전에 확인하세요</strong><ul>{t.success_criteria.map((s,i)=><li key={i}>{s}</li>)}</ul></div>}
        {t.prerequisites.length>0&&<p className="roadmap-muted">선행 작업: {t.prerequisites.map(k=>tasks.find(a=>a.key===k)?.title||k).join(' → ')}</p>}
        {t.personalized_guidance&&<div className="v12-personal-guide"><strong>내 개발 수준에 맞춘 안내</strong><p>{t.personalized_guidance.intro}</p><p><strong>시작 전에:</strong> {t.personalized_guidance.preparation}</p>{!!t.personalized_guidance.waiting_on_titles.length&&<p className="v12-warning">먼저 완료할 작업: {t.personalized_guidance.waiting_on_titles.join(', ')}</p>}<ol>{t.personalized_guidance.checklist.map((step,i)=><li key={i}>{step}</li>)}</ol><p><strong>도움이 필요할 때:</strong> {t.personalized_guidance.help_guidance}</p>{t.personalized_guidance.blocked_help&&<p className="v12-warning">막힘 해결 제안: {t.personalized_guidance.blocked_help}</p>}{t.personalized_guidance.objective_note&&<small>현재 목표: {t.personalized_guidance.objective_note}</small>}</div>}
        <div className="roadmap-task-controls"><p className="roadmap-muted">시작 전 준비: 선행 작업과 인수 자료를 확인하세요. 도움을 받아야 할 때: 실행 오류·권리 문제가 생기면 전문가와 검토하세요.</p><label>작업 상태<select className="input select" value={t.status||'NOT_STARTED'} onChange={e=>progress(t,e.target.value as Status)} disabled={busy}>{Object.entries(statusLabels).map(([s,label])=><option key={s} value={s} disabled={isBlocked(t)&&(s==='IN_PROGRESS'||s==='COMPLETED')}>{label}</option>)}</select></label>
         {(t.status==='BLOCKED'||blockReasons[t.id||''])&&<label>막힘 사유<select className="input select" value={blockReasons[t.id||'']??t.blocked_reason??'OTHER'} onChange={e=>setBlockReasons(prev=>({...prev,[t.id||'']:e.target.value}))}><option value="ENV_SETUP">설치·환경 문제</option><option value="MISSING_FILE">파일·자료 누락</option><option value="RUNTIME_ERROR">실행 오류</option><option value="UNFAMILIAR_TECH">낯선 기술</option><option value="OTHER">기타</option></select></label>}
         <label>내 작업 메모<textarea className="input textarea" maxLength={2000} rows={3} value={notes[t.id||'']??t.buyer_note??''} onChange={e=>setNotes(a=>({...a,[t.id||'']:e.target.value}))} placeholder="진행 내용, 어려운 점, 전문가에게 물어볼 내용을 적어두세요."/></label>
         <button className="btn outline" disabled={busy} onClick={()=>progress(t,t.status||'NOT_STARTED')}>메모 및 상태 저장</button>
         {onSupportRequest&&<button className="btn outline" type="button" onClick={()=>onSupportRequest(t.id||'')}>이 작업으로 판매자에게 도움 요청</button>}{!!t.support_case_ids?.length&&<small>연결된 문의 {t.support_case_ids.length}건</small>}</div>
      </div>}
    </article>)}
   </div>)}
   <div className="roadmap-custom"><button type="button" onClick={()=>setAdding(x=>!x)} className="roadmap-toggle"><Plus size={16}/> {adding?'추가 취소':'내 작업 추가'}</button>
   {adding&&<form onSubmit={add} className="roadmap-custom-form"><label>작업 제목<input className="input" required minLength={3} maxLength={120} value={title} onChange={e=>setTitle(e.target.value)} placeholder="예: 홈페이지 검색 기능 개선"/></label>
    <label>할 일과 확인 방법<textarea className="input textarea" required minLength={10} maxLength={1500} rows={3} value={detail} onChange={e=>setDetail(e.target.value)} placeholder="직접 해야 할 작업과 완료 조건을 구체적으로 적어보세요."/></label>
    <div className="roadmap-form-grid"><label>단계<select className="input select" value={phase} onChange={e=>setPhase(e.target.value)}>{plan.phases?.map(p=><option key={p.key} value={p.key}>{p.label}</option>)}</select></label>
      <label>난이도<select className="input select" value={difficulty} onChange={e=>setDifficulty(e.target.value as Difficulty)}>{Object.entries(difficultyLabels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
      <label>도움 수준<select className="input select" value={assistance} onChange={e=>setAssistance(e.target.value as Assistance)}>{Object.entries(assistanceLabels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
      <label>선행 작업 (선택)<select className="input select" value={prerequisite} onChange={e=>setPrerequisite(e.target.value)}><option value="">없음</option>{tasks.map(t=><option key={t.key} value={t.key}>{t.title}</option>)}</select></label></div>
    <button type="submit" className="btn primary" disabled={busy}>작업 추가하기</button></form>}
   </div>
   <p className="roadmap-disclaimer"><RefreshCcw size={15}/>{plan.disclaimer}</p>
  </>}
 </section>
}
