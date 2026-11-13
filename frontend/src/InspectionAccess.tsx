import React,{useEffect,useState} from 'react';
import {api,body,errorText} from './api';

type Access={id:string;asset_id:string;principal_user_id:string;purpose:string;expires_at:string;revoked_at:string|null};
type Asset={id:string;file_name:string;upload_status:string;malware_scan_status:string};
export function InspectionAccess({assets,userId}:{assets:Asset[];userId:string}){
 const [chosen,setChosen]=useState(''),[principal,setPrincipal]=useState(userId),[purpose,setPurpose]=useState('인수 전 소스코드 정적 실사 및 인계 가능성 평가'),[hours,setHours]=useState(3);
 const [consent,setConsent]=useState(false),[items,setItems]=useState<Access[]>([]),[err,setErr]=useState(''),[msg,setMsg]=useState(''),[busy,setBusy]=useState(false);
 const approved=assets.filter(a=>a.upload_status==='APPROVED');
 useEffect(()=>{if(!approved.some(a=>a.id===chosen))setChosen(approved[0]?.id||'')},[assets]);
 async function refresh(){if(!chosen){setItems([]);return}try{const x=await api<{items:Access[]}>(`/assets/${chosen}/inspection-accesses`);setItems(x.items)}catch(e){setErr(errorText(e))}}
 useEffect(()=>{refresh()},[chosen]);
 async function create(){setBusy(true);setErr('');try{await api(`/assets/${chosen}/inspection-accesses`,body({principal_user_id:principal,purpose,expires_in_hours:hours,consent}));setMsg('파일 단위 실사 권한이 발급됐습니다. 지정된 사용자에게 별도의 asset:inspect 권한이 있는 에이전트 토큰도 필요합니다.');setConsent(false);await refresh()}catch(e){setErr(errorText(e))}finally{setBusy(false)}}
 async function revoke(id:string){setBusy(true);try{await api(`/assets/inspection-accesses/${id}/revoke`,body({}));setMsg('검사 권한이 철회됐습니다.');await refresh()}catch(e){setErr(errorText(e))}finally{setBusy(false)}}
 return <section className="op-section"><h2>판매자 승인형 에이전트 파일 실사</h2><p className="op-sub">Streamlit 에이전트가 비공개 파일의 원본 바이트를 읽으려면 판매자가 대상 사용자·파일·목적·기간을 개별 승인해야 합니다. 이 권한은 다운로드/실행 안전 보증이 아니며, 소유권 이전도 아닙니다.</p>
 {approved.length?<div className="form-stack">
 <label className="field"><span>실사 허용 파일</span><select className="input select" value={chosen} onChange={e=>setChosen(e.target.value)}>{approved.map(a=><option value={a.id} key={a.id}>{a.file_name} · 악성코드 검사 {a.malware_scan_status}</option>)}</select></label>
 <label className="field"><span>권한을 줄 사용자 ID (기본: 내 계정의 에이전트)</span><input className="input" value={principal} onChange={e=>setPrincipal(e.target.value)} maxLength={36}/></label>
 <label className="field"><span>검사 목적</span><input className="input" maxLength={240} value={purpose} onChange={e=>setPurpose(e.target.value)}/></label>
 <label className="field"><span>사용 가능 시간</span><select className="input select" value={hours} onChange={e=>setHours(Number(e.target.value))}><option value={1}>1시간</option><option value={3}>3시간</option><option value={6}>6시간</option><option value={12}>12시간</option></select></label>
 <label className="checkline"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>선택한 사용자에게 선택 파일의 원본을 실사 목적으로 일시 열람하도록 허용합니다. 제3자 소스코드가 포함되지 않았는지 확인했습니다.</label>
 <button className="btn primary" type="button" disabled={busy||!chosen||!consent||purpose.trim().length<10||principal.length!==36} onClick={create}>파일 실사 권한 승인</button>
 </div>:<p className="op-sub">관리자가 검토를 승인한 비공개 파일이 먼저 필요합니다.</p>}
 {err&&<p className="notice error" role="alert">{err}</p>}{msg&&<p className="notice ok">{msg}</p>}
 {items.map(a=><div className="op-item" key={a.id}><div><strong>{a.principal_user_id===userId?'내 계정 에이전트':a.principal_user_id} · {a.revoked_at?'철회됨':'시간 제한'}</strong><span>{a.purpose} · {new Date(a.expires_at).toLocaleString('ko-KR')}까지</span></div>{!a.revoked_at&&<button className="op-button secondary" onClick={()=>revoke(a.id)}>철회</button>}</div>)}
 </section>
}
