import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {api,put,errorText} from './api';

type Preferences={min_budget_krw:number;max_budget_krw:number;skill_level:string;objectives:string[];preferred_tech_stack:string[];max_monthly_cost_krw:number|null;risk_tolerance:string};
const defaults:Preferences={min_budget_krw:0,max_budget_krw:1000000,skill_level:'BASIC',objectives:[],preferred_tech_stack:[],max_monthly_cost_krw:null,risk_tolerance:'MEDIUM'};
export function BuyerProfile(){
 const [prefs,setPrefs]=useState<Preferences>(defaults),[busy,setBusy]=useState(false),[err,setErr]=useState(''),[success,setSuccess]=useState(false);
 const [objectivesText,setObjectivesText]=useState(''),[stackText,setStackText]=useState('');
 useEffect(()=>{api<Preferences>('/buyer-preferences/me').then(p=>{setPrefs(p);setObjectivesText(p.objectives.join(', '));setStackText(p.preferred_tech_stack.join(', '))}).catch(e=>setErr(errorText(e)))},[]);
 function value<K extends keyof Preferences>(key:K,v:Preferences[K]){setPrefs(old=>({...old,[key]:v}));setSuccess(false)}
 async function save(e:React.FormEvent){e.preventDefault();setBusy(true);setErr('');try{
   await api('/buyer-preferences/me',put({...prefs,objectives:objectivesText.split(',').map(x=>x.trim()).filter(Boolean),preferred_tech_stack:stackText.split(',').map(x=>x.trim()).filter(Boolean)}));setSuccess(true)
  }catch(e){setErr(errorText(e))}finally{setBusy(false)}}
 return <main className="page-container narrow"><Link className="back-link" to="/dashboard">← 내 활동</Link><div className="page-heading"><p className="eyebrow">BUYER PROFILE</p><h1>구매 희망 조건</h1><p className="subheading">Streamlit 에이전트가 허용된 범위 안에서 맞춤 매물을 추천할 때 사용하는 기준입니다.</p></div>
 <form onSubmit={save} className="editor-panel form-stack">
  <label className="field"><span>최소 구매 예산 (원)</span><input className="input" type="number" min="0" value={prefs.min_budget_krw} onChange={e=>value('min_budget_krw',Number(e.target.value))}/></label>
  <label className="field"><span>최대 구매 예산 (원)</span><input className="input" type="number" min="0" value={prefs.max_budget_krw} onChange={e=>value('max_budget_krw',Number(e.target.value))}/></label>
  <label className="field"><span>내 기술 수준</span><select className="input select" value={prefs.skill_level} onChange={e=>value('skill_level',e.target.value)}><option value="NONE">코딩 경험 없음</option><option value="BASIC">기초</option><option value="INTERMEDIATE">중급</option><option value="ADVANCED">고급</option></select></label>
  <label className="field"><span>구매 목적 (쉼표로 구분)</span><textarea className="input textarea" value={objectivesText} onChange={e=>{setObjectivesText(e.target.value);setSuccess(false)}} rows={2} placeholder="직접 운영, 코드 학습, 기능 재사용"/></label>
  <label className="field"><span>선호 기술 (쉼표로 구분)</span><input className="input" value={stackText} onChange={e=>{setStackText(e.target.value);setSuccess(false)}} placeholder="Python, React"/></label>
  <label className="field"><span>허용할 최대 월 운영비 (원, 공란은 제한 없음)</span><input className="input" type="number" min="0" value={prefs.max_monthly_cost_krw??''} onChange={e=>value('max_monthly_cost_krw',e.target.value===''?null:Number(e.target.value))}/></label>
  <label className="field"><span>프로젝트 인수 위험 감수 성향</span><select className="input select" value={prefs.risk_tolerance} onChange={e=>value('risk_tolerance',e.target.value)}><option value="LOW">낮음 — 운영 가능한 프로젝트 선호</option><option value="MEDIUM">보통</option><option value="HIGH">높음 — 미완성 프로젝트도 검토</option></select></label>
  <p className="fine">에이전트 추천은 실제 인수 가능성이나 투자 수익을 보장하지 않습니다. 이 정보는 외부 에이전트에 해당 권한을 위임했을 때만 전달됩니다.</p>
  {err&&<p className="notice error" role="alert">{err}</p>}{success&&<p className="notice ok">구매 조건을 저장했습니다.</p>}
  <button type="submit" className="btn primary" disabled={busy}>{busy?'저장 중…':'구매 조건 저장'}</button>
 </form></main>
}
