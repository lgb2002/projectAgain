export function readableTerms(terms:Record<string,unknown>|null|undefined){
 if(!terms||!Object.keys(terms).length)return '추가 조건 없음';
 const keys:Record<string,string>={handover_terms:'인계·지원 조건',handover_days:'희망 인계 기간',message:'상대방 메시지',support_days:'지원 기간',note:'메모'};
 return Object.entries(terms).map(([k,v])=>`${keys[k]||'기타 조건'}: ${typeof v==='string'?v:typeof v==='number'?`${v}${k.includes('days')?'일':''}`:'상세 조건 있음'}`).join(' · ');
}
export function shortDate(dateString:string){try{return new Date(dateString).toLocaleString('ko-KR')}catch{return '기록 없음'}}
