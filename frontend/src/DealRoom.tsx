import React,{useCallback,useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {api,body,errorText} from './api';
import {rights,statuses} from './types';
import {useActionDialog} from './ActionDialog';
import {readableTerms} from './uxHelpers';

type Snapshot={listing_title:string;price_krw:number;rights_type:string;inventory_mode:string;included_assets:string[];excluded_assets:string[];known_defects:string[];required_services:string[];offer_terms:Record<string,unknown>;handover_days_estimate:number|null;seller_support_days:number|null;notice:string;payment_state:string;ownership_transfer_state:string};
type Agreement={id:string;status:string;snapshot:Snapshot;snapshot_sha256:string;buyer_ack_at:string|null;seller_ack_at:string|null;created_at:string};
type Cancel={id:string;requested_by:string;reason:string;status:string;response_note:string|null;created_at:string};
type Dispute={id:string;transaction_id:string;opened_by:string;reason_code:string;description:string;evidence_refs:string[];status:string;counterparty_response:string|null;admin_decision:string|null;admin_reason:string|null;created_at:string};
type Event={id:string;actor_id:string;event_type:string;details:Record<string,unknown>;created_at:string};
type DealTransaction={id:string;listing_id:string;status:string;buyer_id:string;seller_id:string;is_demo:boolean};
const money=(v:number)=>new Intl.NumberFormat('ko-KR').format(v)+'원';
const format=(s:string|null|undefined)=>s?new Date(s).toLocaleString('ko-KR'):'아직 확인 전';
const eventNames:Record<string,string>={AGREEMENT_PREPARED:'거래 조건 기록 생성',DEAL_CREATED:'모의 거래 생성',AGREEMENT_ACKNOWLEDGED:'거래 조건 확인',HANDOVER_STAGE_CHANGED:'인계 단계 변경',CANCELLATION_REQUESTED:'거래 취소 요청',CANCELLATION_ACCEPTED:'거래 취소 동의',CANCELLATION_REJECTED:'거래 취소 거절',DISPUTE_OPENED:'분쟁 접수',DISPUTE_RESPONDED:'분쟁 상대방 답변',DISPUTE_RESOLVED:'분쟁 검토 완료'};
const disputeNames:Record<string,string>={MISSING_ASSET:'전달 자산 누락',MISREPRESENTATION:'매물 정보 상이',RIGHTS_CONCERN:'권리 관련 문제',HANDOVER_DELAY:'인계 지연',OTHER:'기타'};

export function DealRoom({transactionId,userId,onChange}:{transactionId:string;userId:string;onChange?:()=>void}){
 const dialog=useActionDialog();
 const [tx,setTx]=useState<DealTransaction|null>(null);
 const [agreement,setAgreement]=useState<Agreement|null>(null);
 const [cancellations,setCancellations]=useState<Cancel[]>([]);
 const [disputes,setDisputes]=useState<Dispute[]>([]);
 const [events,setEvents]=useState<Event[]>([]);
 const [agree1,setAgree1]=useState(false);const [agree2,setAgree2]=useState(false);
 const [cancelReason,setCancelReason]=useState('');const [disputeReason,setDisputeReason]=useState('MISSING_ASSET');const [disputeText,setDisputeText]=useState('');
 const [response,setResponse]=useState('');const [err,setErr]=useState('');const [msg,setMsg]=useState('');const [busy,setBusy]=useState(false);
 const refresh=useCallback(async()=>{
  const [t,a,c,d,e]=await Promise.all([
   api<DealTransaction>(`/transactions/${transactionId}`),
   api<{agreement:Agreement|null}>(`/transactions/${transactionId}/agreement`),
   api<{items:Cancel[]}>(`/transactions/${transactionId}/cancellations`),
   api<{items:Dispute[]}>(`/transactions/${transactionId}/disputes`),
   api<{items:Event[]}>(`/transactions/${transactionId}/deal-events`)]);
  setTx(t);setAgreement(a.agreement);setCancellations(c.items);setDisputes(d.items);setEvents(e.items);
 },[transactionId]);
 useEffect(()=>{refresh().catch(e=>setErr(errorText(e)))},[refresh]);
 async function action(path:string,payload:unknown,success='처리 내용이 저장되었습니다.'){
  setBusy(true);setErr('');setMsg('');
  try{await api(path,body(payload));await refresh();onChange?.();setMsg(success);return true;}
  catch(e){setErr(errorText(e));return false;}
  finally{setBusy(false)}
 }
 if(!tx)return <section className="deal-section"><h2>거래 조건·분쟁 관리</h2>{err||'거래 정보를 불러오는 중입니다.'}</section>;
 const buyer=tx.buyer_id===userId;
 const finished=['CANCELLED','DEMO_COMPLETED'].includes(tx.status);
 const pendingCancel=cancellations.find(x=>x.status==='PENDING');
 const activeDispute=disputes.find(x=>x.status==='OPEN');
 const hasAck=!!(buyer?agreement?.buyer_ack_at:agreement?.seller_ack_at);
 const acknowledged=agreement?.status==='ACKNOWLEDGED';
 return <section className="deal-section">
  <div className="deal-header"><div><p className="eyebrow">DEAL WORKSPACE</p><h2>거래 조건 및 계약 기록</h2></div><span className="deal-demo">시연 전용 · 결제 없음</span></div>
  <p className="deal-muted">이 화면의 확인은 플랫폼 내 모의 조건 확인입니다. 법적 효력이 보장되는 전자서명이나 저작권 양도 계약, 결제·에스크로·환불·정산을 수행하지 않습니다.</p>
  {err&&<p className="deal-error" role="alert">{err}</p>}{msg&&<p className="deal-success" role="status">{msg}</p>}
  {!agreement&&!finished&&<div className="deal-panel"><p>이전 버전에서 생성된 거래입니다. 조건 기록을 먼저 생성할 수 있습니다.</p><button className="btn primary" disabled={busy} onClick={()=>action(`/transactions/${transactionId}/agreement/prepare`,{})}>거래 조건 기록 생성</button></div>}
  {agreement&&<div className="deal-panel">
   <div className="deal-row"><h3>합의된 거래 조건 · 고정 기록</h3><span className="deal-status">{acknowledged?'양측 확인 완료':'양측 확인 대기'}</span></div>
   <div className="deal-record"><div><small>프로젝트</small><strong>{agreement.snapshot.listing_title}</strong></div><div><small>합의 금액 (실제 청구 없음)</small><strong>{money(agreement.snapshot.price_krw)}</strong></div><div><small>권리 유형 · 판매자 진술</small><strong>{rights[agreement.snapshot.rights_type]||agreement.snapshot.rights_type}</strong></div><div><small>예상 인수 기간</small><strong>{agreement.snapshot.handover_days_estimate??'미기재'}일</strong></div></div>
   <h4>포함 자산</h4><ul>{agreement.snapshot.included_assets.map((s,i)=><li key={i}>{s}</li>)}</ul>
   <h4>제외 자산</h4><ul>{agreement.snapshot.excluded_assets.length?agreement.snapshot.excluded_assets.map((s,i)=><li key={i}>{s}</li>):<li>별도 기재 없음</li>}</ul>
   <details className="deal-terms"><summary>기존 제안 조건·알려진 결함·필요 서비스 확인</summary><h4>제안 조건</h4><pre>{readableTerms(agreement.snapshot.offer_terms)}</pre><h4>알려진 결함</h4><ul>{agreement.snapshot.known_defects.map((x,i)=><li key={i}>{x}</li>)}</ul><h4>필요 서비스</h4><ul>{agreement.snapshot.required_services.map((x,i)=><li key={i}>{x}</li>)}</ul></details>
   <a className="plain-link" href={`/api/v1/transactions/${transactionId}/agreement/document`}>시연용 거래 조건 확인서 (.txt) 내려받기</a>
   <details className="deal-technical"><summary>기술 기록 및 검증용 해시</summary><p className="deal-digest">SHA-256: <code>{agreement.snapshot_sha256}</code></p></details>
   <div className="deal-confirmations"><span>구매자: {format(agreement.buyer_ack_at)}</span><span>판매자: {format(agreement.seller_ack_at)}</span></div>
   {!hasAck&&!finished&&tx.status!=='DISPUTED'&&<div className="deal-ack">
    <label><input type="checkbox" checked={agree1} onChange={e=>setAgree1(e.target.checked)}/> 위 거래 조건과 포함·제외 자산을 확인했습니다.</label>
    <label><input type="checkbox" checked={agree2} onChange={e=>setAgree2(e.target.checked)}/> 실제 결제·소유권 이전이 없는 시연 절차임을 이해했습니다.</label>
    <button className="btn primary" disabled={busy||!agree1||!agree2} onClick={()=>action(`/transactions/${transactionId}/agreement/acknowledge`,{snapshot_sha256:agreement.snapshot_sha256,understood_demo_only:true,confirmed_terms:true},'모의 거래 조건 확인이 기록됐습니다.')}>내 조건 확인 기록 남기기</button>
   </div>}
   {hasAck&&!acknowledged&&<p className="deal-muted">상대방의 확인을 기다리는 중입니다. 양측 확인 후 인수인계를 진행할 수 있습니다.</p>}
  </div>}
  <details className="deal-panel deal-fold" open={Boolean(pendingCancel)}><summary>거래 취소 및 요청 내역 {pendingCancel?"· 응답 필요":""}</summary><div className="deal-row"><h3>거래 취소 합의</h3><span className="deal-status">상호 동의 필요</span></div>
   <p className="deal-muted">신청자가 스스로 취소를 승인할 수 없습니다. 이미 받은 자료는 취소해도 자동 회수되지 않습니다.</p>
   {cancellations.map(c=><div className="deal-item" key={c.id}><strong>{c.status==='PENDING'?'상대방 응답 대기':c.status==='ACCEPTED'?'양측 취소 합의':c.status==='REJECTED'?'취소 거절':c.status}</strong><p>{c.reason}</p>{c.response_note&&<p>답변: {c.response_note}</p>}{c.status==='PENDING'&&c.requested_by!==userId&&!finished&&<div className="deal-actions"><button className="btn outline" disabled={busy} onClick={async()=>{const note=await dialog.ask({title:'거래 취소 요청 거절',description:'상대방에게 전달할 사유를 작성해 주세요.',minimum:5,confirmText:'거절 사유 제출'});if(note)await action(`/transactions/${transactionId}/cancellations/${c.id}/respond`,{accept:false,response_note:note})}}>거절</button><button className="btn primary" disabled={busy} onClick={async()=>{const note=await dialog.ask({title:'거래 취소 동의 사유',description:'매물 예약 상태가 해제됩니다. 이미 전달한 파일은 자동 회수되지 않습니다.',minimum:5,confirmText:'내용 확인',danger:true});if(!note)return;if(await dialog.confirm({title:'정말 모의 거래를 취소할까요?',description:'거래가 취소되며 기존 인수인계 진행을 되돌릴 수 없습니다.',danger:true,confirmText:'취소 동의 확정'}))await action(`/transactions/${transactionId}/cancellations/${c.id}/respond`,{accept:true,response_note:note})}}>취소에 동의</button></div>}</div>)}
   {!finished&&!pendingCancel&&tx.status!=='DISPUTED'&&<div className="deal-form"><label>취소 요청 사유 (10자 이상)</label><textarea className="input" rows={2} maxLength={2000} value={cancelReason} onChange={e=>setCancelReason(e.target.value)} placeholder="거래를 취소하려는 이유를 구체적으로 적어주세요."/><button className="btn outline" disabled={busy||cancelReason.trim().length<10} onClick={()=>{action(`/transactions/${transactionId}/cancellations`,{reason:cancelReason}).then(ok=>{if(ok)setCancelReason('')})}}>상대방에게 취소 요청</button></div>}
  </details>
  <details className="deal-panel deal-fold" open={Boolean(activeDispute)}><summary>분쟁 접수 및 처리 내역 {activeDispute?"· 처리 중":""}</summary><div className="deal-row"><h3>분쟁 접수·해결</h3><span className="deal-status">관리자 검토</span></div>
   {disputes.map(d=><div className="deal-item" key={d.id}><strong>{disputeNames[d.reason_code]||d.reason_code} · {d.status==='OPEN'?'검토 중':'종결'}</strong><p>{d.description}</p>{d.counterparty_response&&<p>상대방 답변: {d.counterparty_response}</p>}{d.admin_decision&&<p>관리자 결정: {d.admin_decision==='CANCEL_DEMO'?'모의 거래 취소':'인계 재개'} · {d.admin_reason}</p>}{d.status==='OPEN'&&d.opened_by!==userId&&!d.counterparty_response&&<div className="deal-form"><textarea className="input" rows={2} value={response} maxLength={3000} onChange={e=>setResponse(e.target.value)} placeholder="상대방 주장에 대한 의견을 입력하세요."/><button className="btn outline" disabled={busy||response.trim().length<10} onClick={()=>action(`/transactions/${transactionId}/disputes/${d.id}/respond`,{response}).then(ok=>{if(ok)setResponse('')})}>분쟁에 답변</button></div>}</div>)}
   {!finished&&!activeDispute&&<div className="deal-form"><label>분쟁 사유</label><select className="input" value={disputeReason} onChange={e=>setDisputeReason(e.target.value)}>{Object.entries(disputeNames).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select><label>구체적인 내용 (15자 이상)</label><textarea className="input" rows={3} maxLength={4000} value={disputeText} onChange={e=>setDisputeText(e.target.value)} placeholder="거래 조건과 실제 전달 내용의 차이를 적어주세요."/><button className="btn outline" disabled={busy||disputeText.trim().length<15} onClick={async()=>{if(await dialog.confirm({title:'분쟁을 접수할까요?',description:'관리자가 검토하는 동안 인수인계 단계가 일시 중단됩니다. 접수 내용을 다시 확인하세요.',danger:true,confirmText:'분쟁 접수'})){const ok=await action(`/transactions/${transactionId}/disputes`,{reason_code:disputeReason,description:disputeText,evidence_refs:[]});if(ok)setDisputeText('')}}}>관리자에게 분쟁 접수</button></div>}
  </details>
  <details className="deal-panel deal-fold"><summary>거래 이력 자세히 보기</summary><h3>거래 이력</h3><p className="deal-muted">이력은 모의 거래의 작업 증빙입니다. 금전 이동 증빙이 아닙니다.</p><ol className="deal-timeline">{events.length?events.map(e=><li key={e.id}><strong>{eventNames[e.event_type]||e.event_type}</strong><small>{format(e.created_at)} · {e.actor_id===userId?'본인':'상대방 또는 관리자'}</small></li>):<li>기록된 이력이 없습니다.</li>}</ol>
  </details>
  <Link className="plain-link" to="/dashboard?tab=transactions">내 거래 목록으로 돌아가기</Link>{dialog.dialog}
 </section>
}

type AdminDetail={transaction:DealTransaction;agreement:Agreement|null;cancellations:Cancel[];disputes:Dispute[];events:Event[]};
export function AdminDealReview(){
 const dialog=useActionDialog();
 const [selected,setSelected]=useState<AdminDetail|null>(null);
 const [cases,setCases]=useState<Dispute[]>([]);const [txs,setTxs]=useState<DealTransaction[]>([]);const [err,setErr]=useState('');const [busy,setBusy]=useState(false);
 async function loadDetail(id:string){try{const detail=await api<AdminDetail>(`/admin/deal-transactions/${id}`);setSelected(detail);setErr('')}catch(e){setErr(errorText(e))}}
 const refresh=useCallback(async()=>{const [d,t]=await Promise.all([api<{items:Dispute[]}>('/admin/deal-disputes'),api<{items:DealTransaction[]}>('/admin/deal-transactions')]);setCases(d.items);setTxs(t.items)},[]);
 useEffect(()=>{refresh().catch(e=>setErr(errorText(e)))},[refresh]);
 async function decide(id:string,decision:'RESUME_HANDOVER'|'CANCEL_DEMO'){
  const reason=await dialog.ask({title:'관리자 분쟁 처리 근거',description:'모의 거래 상태 변경 사유를 구체적으로 남겨 주세요. 법적 분쟁 해결을 의미하지 않습니다.',minimum:15,confirmText:'다음'});
  if(!reason)return;
  if(!await dialog.confirm({title:'처리 결과를 확정할까요?',description:decision==='CANCEL_DEMO'?'모의 거래를 취소합니다. 취소 후 되돌릴 수 없습니다.':'인수인계 절차를 다시 진행할 수 있도록 변경합니다.',danger:decision==='CANCEL_DEMO',confirmText:'관리자 결정 기록'}))return;
  setBusy(true);setErr('');try{await api(`/admin/deal-disputes/${id}/decide`,body({decision,reason}));await refresh()}catch(e){setErr(errorText(e))}finally{setBusy(false)}
 }
 return <section className="deal-section"><div className="deal-header"><h2>모의 거래 · 분쟁 관리</h2><span className="deal-demo">실제 정산 없음</span></div>{err&&<p className="deal-error">{err}</p>}
  <div className="deal-panel"><h3>관리자 검토 대기</h3>{!cases.some(c=>c.status==='OPEN')&&<p className="deal-muted">진행 중인 분쟁이 없습니다.</p>}{cases.filter(c=>c.status==='OPEN').map(c=><div className="deal-item" key={c.id}><strong>{disputeNames[c.reason_code]||c.reason_code}</strong><p>{c.description}</p><small>거래 ID: {c.transaction_id}</small>{c.counterparty_response&&<p>상대방 의견: {c.counterparty_response}</p>}<div className="deal-actions"><button className="btn outline" disabled={busy} onClick={()=>decide(c.id,'RESUME_HANDOVER')}>인계 재개</button><button className="btn danger" disabled={busy} onClick={()=>decide(c.id,'CANCEL_DEMO')}>모의 거래 취소</button></div></div>)}</div>
  <div className="deal-panel"><h3>최근 거래</h3>{txs.map(t=><div className="deal-item" key={t.id}><strong>{statuses[t.status]||t.status}</strong><p>거래 ID: {t.id}</p><p>매물 ID: {t.listing_id}</p><button className="btn outline" onClick={()=>loadDetail(t.id)}>거래 기록 보기</button></div>)}{selected&&<div className="deal-item"><div className="deal-row"><strong>거래 기록 상세 · {selected.transaction.id}</strong><button className="btn outline" onClick={()=>setSelected(null)}>닫기</button></div><p>상태: {statuses[selected.transaction.status]||selected.transaction.status}</p><p>가상 금액: {selected.agreement?money(selected.agreement.snapshot.price_krw):'기록 준비 전'}</p><p>시연 조건 확인: {selected.agreement?.status||'미준비'}</p><p>취소 요청: {selected.cancellations.length}건 · 분쟁: {selected.disputes.length}건</p><div className="deal-timeline">{selected.events.map((e,i)=><div key={i}><strong>{eventNames[e.event_type]||e.event_type}</strong><small>{format(e.created_at)}</small></div>)}</div></div>}</div>
 {dialog.dialog}</section>
}
