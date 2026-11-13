import React,{useEffect,useState} from 'react';
import {Github,FileArchive,Link2,RefreshCw,ShieldCheck,AlertTriangle,CheckCircle2,LockKeyhole,ArrowRight,Unplug} from 'lucide-react';
import {api,body,errorText,uploadSourceZip} from './api';

export type SourceAnalysis={
  analysis_version:string;level:string;code_executed:boolean;llm_used:boolean;file_count:number;
  languages:string[];tech_stack:string[];possible_features:string[];possible_services:string[];
  signals:Record<string,boolean>;warnings:string[];readiness:string;
  description_suggestion:string;included_assets_suggestion:string[];excluded_assets_suggestion:string[];disclaimer:string;
  ci_evidence?:{status:string;runs_checked:number;observed_sha_match:boolean};
};
export type SourceImport={
  id:string;source_type:'GITHUB'|'ZIP';source_label:string;source_private:boolean;revision:string|null;
  size_bytes:number;checksum_sha256:string;expires_at:string;analysis:SourceAnalysis;
  asset_review_status:string;malware_scan_status:string;
};
type Repo={full_name:string;private:boolean;installation_id:number;description:string};
type GhStatus={configured:boolean;connected:boolean;github_login:string|null;public_url_import:boolean;install_url:string|null};

export function ImportPanel({value,onChange}:{value:SourceImport|null;onChange:(source:SourceImport|null)=>void}){
  const [method,setMethod]=useState<'github'|'zip'|'manual'>('github');
  const [status,setStatus]=useState<GhStatus|null>(null);
  const [repos,setRepos]=useState<Repo[]>([]);
  const [repoChoice,setRepoChoice]=useState('');
  const [url,setUrl]=useState('');
  const [zip,setZip]=useState<File|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [repoLoading,setRepoLoading]=useState(false);
  const [repoError,setRepoError]=useState('');

  async function fetchRepos(){
    setRepoLoading(true);setRepoError('');
    try{const data=await api<{items:Repo[];truncated:boolean}>('/github/repositories');setRepos(data.items);
      if(data.truncated)setRepoError('표시 가능한 저장소가 많아 일부만 표시했습니다.');
    }catch(e){setRepoError(errorText(e))}finally{setRepoLoading(false)}
  }
  useEffect(()=>{api<GhStatus>('/github/status').then(s=>{setStatus(s);if(s.connected)fetchRepos()}).catch(()=>{})},[]);
  async function connect(){
    setError('');
    try{const r=await api<{authorize_url:string}>('/github/connect',body({}));
      const u=new URL(r.authorize_url);
      if(u.protocol!=='https:'||u.hostname!=='github.com')throw new Error('GitHub 연결 주소를 확인할 수 없습니다.');
      window.location.assign(r.authorize_url);
    }catch(e){setError(errorText(e))}
  }
  async function disconnect(){
    try{await api('/github/connection',{method:'DELETE'});setRepos([]);setRepoChoice('');
      setStatus(s=>s?{...s,connected:false,github_login:null}:s)}catch(e){setError(errorText(e))}
  }
  async function analyze(){
    setError('');setBusy(true);
    try{
      let result:SourceImport;
      if(method==='zip'){
        if(!zip)throw new Error('ZIP 파일을 선택하세요.');
        result=await uploadSourceZip<SourceImport>(zip);
      }else{
        const repo=repos.find(r=>`${r.installation_id}:${r.full_name}`===repoChoice);
        const repository=repo?.full_name||url.trim();
        if(!repository)throw new Error('저장소를 선택하거나 공개 GitHub URL을 입력하세요.');
        result=await api<SourceImport>('/listing-imports/github',body({repository,installation_id:repo?.installation_id||null}));
      }
      onChange(result);
    }catch(e){setError(errorText(e))}finally{setBusy(false)}
  }
  return <section className="import-panel" aria-label="프로젝트 자동 등록">
    <div className="import-head"><div><span className="import-eyebrow">가져와서 바로 시작하기</span>
      <h2>프로젝트 정보를 자동으로 준비해 드려요.</h2>
      <p>저장소 또는 ZIP을 읽어 기술 정보와 등록 초안을 제안합니다. 가격·권리·운영 상태는 직접 확인합니다.</p></div>
      <ShieldCheck size={29} strokeWidth={1.5}/></div>
    <div className="import-methods">
      <button type="button" className={method==='github'?'chosen':''} onClick={()=>setMethod('github')}><Github size={20}/> GitHub 저장소</button>
      <button type="button" className={method==='zip'?'chosen':''} onClick={()=>setMethod('zip')}><FileArchive size={20}/> ZIP 파일</button>
      <button type="button" className={method==='manual'?'chosen':''} onClick={()=>setMethod('manual')}><Link2 size={19}/> 직접 작성</button>
    </div>
    {method==='github'&&<div className="import-content">
      {status?.connected?<div className="github-connected"><span><CheckCircle2 size={17}/> <strong>{status.github_login}</strong> 연결됨</span><button type="button" onClick={disconnect}><Unplug size={15}/> 연결 해제</button></div>:
        <div className="github-cta"><p>비공개 저장소까지 불러오려면 GitHub 계정을 연결하세요. 프로젝트 접근 권한은 저장소별로 관리됩니다.</p>
          <button type="button" onClick={connect} disabled={!status?.configured}><Github size={17}/> GitHub 계정 연결</button>
          {!status?.configured&&<small>현재 비공개 GitHub 연결이 설정되지 않았습니다. 공개 저장소 URL은 아래에서 바로 분석할 수 있습니다.</small>}
        </div>}
      {status?.connected&&<label className="import-field">연결된 저장소 선택
        <select value={repoChoice} onChange={e=>{setRepoChoice(e.target.value);if(e.target.value)setUrl('')}} disabled={repoLoading}>
          <option value="">직접 URL을 입력하거나 저장소를 선택하세요</option>
          {repos.map(r=><option key={`${r.installation_id}:${r.full_name}`} value={`${r.installation_id}:${r.full_name}`}>{r.private?'🔒 ':'🌐 '}{r.full_name}</option>)}
        </select>
        {repoError&&<small className="muted">{repoError}</small>}
        {status.install_url&&<a className="github-install" href={status.install_url} target="_blank" rel="noopener noreferrer">GitHub 앱 설치·저장소 권한 선택</a>}
        <button type="button" className="import-subtle" disabled={repoLoading} onClick={fetchRepos}><RefreshCw size={14}/> 목록 새로고침</button>
      </label>}
      <label className="import-field">공개 GitHub 저장소 주소
        <input type="text" value={url} onChange={e=>{setUrl(e.target.value);if(e.target.value)setRepoChoice('')}} placeholder="https://github.com/계정/저장소" disabled={!!repoChoice}/>
      </label>
      <p className="import-note"><LockKeyhole size={15}/> 비공개 소스는 매물 상세 페이지에 노출되지 않습니다. GitHub 접근 권한이 판매 권리까지 증명하지는 않습니다.</p>
    </div>}
    {method==='zip'&&<div className="import-content"><label className="import-zip"> <FileArchive size={25}/>
      <strong>{zip?zip.name:'ZIP 소스코드 파일 선택'}</strong>
      <span>최대 10MB · 압축 구조와 위험 파일 검사 · 코드는 실행하지 않음</span>
      <input type="file" accept=".zip,application/zip" onChange={e=>setZip(e.target.files?.[0]||null)}/>
    </label></div>}
    {method!=='manual'&&<div className="import-actions"><button type="button" onClick={analyze} disabled={busy}>
      {busy?'프로젝트 구조 분석 중…':'소스 분석하고 자동 입력'} <ArrowRight size={17}/></button></div>}
    {method==='manual'&&<p className="import-note">아래 등록 양식에 직접 정보를 작성할 수 있습니다. 소스 없이 등록해도 인수 준비 보고서는 자동 생성됩니다. 소스 파일은 등록 후 거래 업무실에서 업로드할 수 있습니다.</p>}
    {error&&<p role="alert" className="import-error"><AlertTriangle size={17}/>{error}</p>}
    {value&&<div className="import-result">
      <div className="import-result-head"><div><span className="import-eyebrow">정적 분석 완료 · 등록 전 확인</span>
        <h3>{value.source_label}</h3>
        <p>{value.analysis.file_count.toLocaleString()}개 파일 분석 · {value.source_type==='GITHUB'?'GitHub':'ZIP'} · {value.revision?`커밋 ${value.revision} · `:''}{value.source_private?'비공개 원본':''}</p>
      </div><button type="button" className="import-subtle" onClick={()=>onChange(null)}>분석 선택 해제</button></div>
      <div className="import-tags">{value.analysis.tech_stack.map(t=><span key={t}>{t}</span>)}</div>
      <dl className="import-facts"><div><dt>기능 단서</dt><dd>{value.analysis.possible_features.join(' · ')||'코드 경로로 확인 불가'}</dd></div>
        <div><dt>필요할 수 있는 서비스</dt><dd>{value.analysis.possible_services.join(' · ')||'추가 확인 필요'}</dd></div>
        <div><dt>기초 검사</dt><dd>{Object.entries(value.analysis.signals).map(([k,v])=>`${k==='readme'?'설명 문서':k==='tests'?'테스트': '배포 설정'} ${v?'발견':'미확인'}`).join(' · ')}</dd></div>
        <div><dt>확인할 위험</dt><dd>{value.analysis.warnings.length?value.analysis.warnings.join(' · '):'기초 구조 검사에서 누락 항목 없음 (안전 보장 아님)'}</dd></div>
        {value.source_type==='GITHUB'&&<div><dt>GitHub CI 기록</dt><dd>{value.analysis.ci_evidence?.status==='OBSERVED_SUCCESS'?'해당 커밋의 CI 성공 기록 관찰 (실제 실행 보증 아님)':value.analysis.ci_evidence?.status==='OBSERVED_FAILURE'?'해당 커밋에서 CI 실패 기록 관찰':value.analysis.ci_evidence?.status==='OBSERVED_IN_PROGRESS'?'CI 실행 진행 기록 관찰':'조회 가능한 CI 결과 없음 · 별도 검증 필요'}</dd></div>}
      </dl>
      <p className="import-note"><AlertTriangle size={15}/>{value.analysis.disclaimer} 원본은 임시로 비공개 보관되고 매물 저장 시 격리 파일로 연결됩니다. 2시간 이내에 등록하세요.</p>
      <p className="import-applied"><CheckCircle2 size={17}/> 양식에 분석 초안을 채웠습니다. 모든 내용을 확인하고 수정하세요.</p>
    </div>}
  </section>
}
