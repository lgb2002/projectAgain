import React,{useEffect,useState} from 'react';
import {Activity,FileCode2,ShieldAlert} from 'lucide-react';
import {api,body,errorText} from './api';

type Check={key:string;title:string;status:string;basis:string;action:string};
type HandoverReport={available:boolean;analysis:{
  report_version:string;source_analyzed:boolean;scope:string;file_count:number;tech_stack:string[];
  readiness_status:string;ci_evidence:{status:string;runs_checked:number;observed_sha_match:boolean};
  checks:Check[];next_actions:string[];source_warnings:string[];notes:string;
};independent_report_summaries:{report_type:string;verdict:string;reviewer_kind:string;created_at:string}[]};
const statusName:Record<string,string>={DECLARED:'판매자 입력',NEEDS_INPUT:'정보 필요',FILE_FOUND:'파일 발견',NOT_OBSERVED:'확인 필요'};
const ciName:Record<string,string>={OBSERVED_SUCCESS:'GitHub CI 성공 기록 관찰',OBSERVED_FAILURE:'GitHub CI 실패 기록 관찰',
  OBSERVED_IN_PROGRESS:'GitHub CI 진행 중 기록 관찰',NOT_AVAILABLE:'CI 실행 기록 확인되지 않음',QUERY_FAILED:'CI 기록 조회 실패'};

export function SourceReport({listingId,includeDemo,isOwner=false}:{listingId:string;includeDemo:boolean;isOwner?:boolean}){
 const [report,setReport]=useState<HandoverReport|null>(null),[error,setError]=useState(''),[info,setInfo]=useState(''),[running,setRunning]=useState(false);
 async function refresh(){const x=await api<HandoverReport>(`/listings/${listingId}/takeover-report${includeDemo?'?include_demo=true':''}`);setReport(x)}
 useEffect(()=>{let alive=true;api<HandoverReport>(`/listings/${listingId}/takeover-report${includeDemo?'?include_demo=true':''}`)
   .then(x=>{if(alive)setReport(x)}).catch(e=>{if(alive)setError(errorText(e))});return()=>{alive=false}},[listingId,includeDemo]);
 async function reanalyze(){setRunning(true);setError('');setInfo('');try{await api(`/listings/${listingId}/source-summary/reanalyze`,body({}));await refresh();setInfo('저장된 원본을 다시 분석했습니다. 변경된 매물은 관리자 재검토가 필요할 수 있습니다.')}catch(e){setError(errorText(e))}finally{setRunning(false)}}
 const a=report?.analysis;
 return <section className="detail-section source-report" aria-label="인수 준비 보고서">
   <h2><FileCode2 size={21}/> 인수 준비 보고서</h2>
   <p>모든 프로젝트에 제공되는 인수 점검표입니다. 판매자 입력과 실제 관찰 증거를 구분합니다.</p>
   {error&&<p role="alert" className="experience-error">{error}</p>}{info&&<p className="experience-success">{info}</p>}
   {!a?<p>보고서를 불러오지 못했습니다. 새로고침 후 다시 확인해 주세요.</p>:<>
     <div className="source-report-meta"><span><Activity size={15}/> {a.source_analyzed?`${a.file_count.toLocaleString()}개 소스 파일 분석`:'원본 소스 미제공'}</span><span>독립 검증 필요</span></div>
     {!!a.tech_stack?.length&&<p><strong>감지한 기술:</strong> {a.tech_stack.join(' · ')}</p>}
     <div className="takeover-report"><div className="takeover-report-header"><h3>인수 전 확인할 사항</h3><p>판매자 진술, 정적 파일 탐지, 미확인 항목을 함께 보여줍니다.</p></div>
       <div className="takeover-checks">{(a.checks||[]).map(c=><div key={c.key} className="takeover-check"><span className={['FILE_FOUND','DECLARED'].includes(c.status)?'takeover-found':'takeover-review'}>{statusName[c.status]||'확인 필요'}</span>
           <div><strong>{c.title}</strong><p>{c.basis}. {c.action}</p></div></div>)}</div>
       <div className="takeover-next"><strong>GitHub CI 실행 증거</strong><p>{ciName[a.ci_evidence?.status]||'관찰 정보 없음'} · 조회된 실행 {a.ci_evidence?.runs_checked||0}건</p><p className="muted">특정 커밋에서 GitHub가 기록한 결과만 조회합니다. 인수 후 실행 성공을 보증하지 않습니다.</p></div>
       {!!report?.independent_report_summaries?.length&&<div className="takeover-next"><strong>외부 실사 보고 기록</strong><ol>{(report?.independent_report_summaries||[]).map((r,i)=><li key={i}>{r.report_type} · {r.verdict} · {r.reviewer_kind} (제출 자료, 독립 검증 전)</li>)}</ol></div>}
       {!!a.next_actions?.length&&<div className="takeover-next"><strong>우선 확인할 항목</strong><ol>{a.next_actions.map((x,i)=><li key={i}>{x}</li>)}</ol></div>}
     </div>
     {isOwner&&a.source_analyzed&&<div className="source-report-owner"><button type="button" disabled={running} onClick={reanalyze}>{running?'재분석 중…':'비공개 원본 다시 분석'}</button><span>소스 재분석은 실제 실행이 아니며, 기존 GitHub CI 기록은 과거 관찰값으로 남습니다.</span></div>}
     <div className="source-report-disclaimer"><ShieldAlert size={17}/><span>{a.notes} 서버는 업로드된 코드를 실행하지 않습니다. 실제 결제·권리 이전은 제공하지 않습니다.</span></div>
   </>}
 </section>
}
