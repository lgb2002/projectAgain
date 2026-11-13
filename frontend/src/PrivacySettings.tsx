import React,{useEffect,useState} from 'react';
import{api,body,errorText}from'./api';
import{useNavigate}from'react-router-dom';

type Impact={listings:number;negotiations:number;demo_transactions:number;source_archives:number};
export function PrivacySettings({onDeleted}:{onDeleted:()=>Promise<void>}){
 const nav=useNavigate();const [open,setOpen]=useState(false),[password,setPassword]=useState(''),[phrase,setPhrase]=useState('');
 const [summary,setSummary]=useState<{impact:Impact;terms:string;storage_deletion:string}|null>(null);
 const [error,setError]=useState(''),[sending,setSending]=useState(false),[success,setSuccess]=useState('');
 useEffect(()=>{if(open)api<typeof summary>('/auth/privacy/summary').then(setSummary).catch(e=>setError(errorText(e)))},[open]);
 async function remove(e:React.FormEvent){e.preventDefault();if(!password||phrase!=='계정 탈퇴')return;
   setSending(true);setError('');try{
    const r=await api<{account_disabled:boolean;private_objects_queued:number}>('/auth/privacy/delete',body({password,confirmation:phrase}));
    setPassword('');setPhrase('');setSuccess(`계정 접속이 종료됐습니다. 비공개 객체 ${r.private_objects_queued}건은 삭제 워커가 처리합니다.`);
    await onDeleted();nav('/',{replace:true});
   }catch(e){setError(errorText(e))}finally{setSending(false)}
 }
 return <section className="settings-section privacy-settings"><h2>회원 탈퇴 및 개인정보 삭제</h2>
   <p>탈퇴하면 계정 접근과 외부 에이전트 권한이 즉시 중단되며, 내 매물은 공개되지 않습니다. 시연 거래 및 지원도 종료될 수 있습니다.</p>
   {!open?<button type="button" className="btn outline" onClick={()=>setOpen(true)}>탈퇴 시 삭제 범위 확인</button>:<form onSubmit={remove} className="privacy-form">
     {summary?<><p><strong>내 데이터 현황:</strong> 매물 {summary.impact.listings}건 · 협상 {summary.impact.negotiations}건 · 시연 거래 {summary.impact.demo_transactions}건 · 소스 {summary.impact.source_archives}건</p>
       <p>{summary.terms}</p><p>{summary.storage_deletion}</p></>:<p>계정 데이터 확인 중…</p>}
     <label>현재 비밀번호<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required maxLength={200}/></label>
     <label>확인을 위해 <strong>계정 탈퇴</strong>를 입력하세요<input value={phrase} onChange={e=>setPhrase(e.target.value)} required/></label>
     <div className="settings-links"><button type="button" className="btn outline" onClick={()=>{setOpen(false);setPassword('');setPhrase('');setError('')}}>취소</button>
       <button className="btn danger" type="submit" disabled={sending||!summary||!password||phrase!=='계정 탈퇴'}>{sending?'탈퇴 처리 중…':'회원 탈퇴 및 데이터 삭제 요청'}</button></div>
   </form>}
   {error&&<p role="alert" className="experience-error">{error}</p>}{success&&<p role="status" className="experience-success">{success}</p>}
 </section>
}
