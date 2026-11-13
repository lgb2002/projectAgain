import React,{useEffect,useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';

type DialogOptions={title:string;description?:string;defaultValue?:string;minimum?:number;maximum?:number;danger?:boolean;confirmText?:string;inputLabel?:string;numeric?:boolean};
type Request={mode:'text'|'confirm';options:DialogOptions};
/** Accessible replacement for window.prompt/confirm. Returns null when the user cancels. */
export function useActionDialog(){
 const [request,setRequest]=useState<Request|null>(null);
 const [value,setValue]=useState('');
 const [error,setError]=useState('');
 const resolveRef=useRef<((result:string|null)=>void)|null>(null);
 const focusRef=useRef<HTMLTextAreaElement|null>(null);
 const cancelRef=useRef<HTMLButtonElement|null>(null);
 const previousFocus=useRef<HTMLElement|null>(null);
 const titleId=useId();const descId=useId();
 function ask(options:DialogOptions){return new Promise<string|null>(resolve=>{
  if(resolveRef.current)resolveRef.current(null);
  resolveRef.current=resolve;previousFocus.current=document.activeElement as HTMLElement|null;
  setRequest({mode:'text',options});setValue(options.defaultValue||'');setError('');
 })}
 async function confirm(options:DialogOptions){return (await new Promise<string|null>(resolve=>{
  if(resolveRef.current)resolveRef.current(null);
  resolveRef.current=resolve;previousFocus.current=document.activeElement as HTMLElement|null;
  setRequest({mode:'confirm',options});setValue('');setError('');
 }))==='yes'}
 function close(result:string|null){resolveRef.current?.(result);resolveRef.current=null;setRequest(null);setError('');queueMicrotask(()=>previousFocus.current?.focus())}
 useEffect(()=>{if(!request)return;const t=window.setTimeout(()=>{(request.mode==='text'?focusRef.current:cancelRef.current)?.focus()},0);return()=>window.clearTimeout(t)},[request]);
 useEffect(()=>{if(!request)return;
  function onKey(e:KeyboardEvent){if(e.key==='Escape'){e.preventDefault();close(null)}if(e.key==='Tab'){
   const scope=document.querySelector('[data-action-dialog]');if(!scope)return;
   const elements=Array.from(scope.querySelectorAll<HTMLElement>('button:not([disabled]),textarea:not([disabled])'));
   if(!elements.length)return;const first=elements[0],last=elements[elements.length-1];
   if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
   else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
  }}
  document.addEventListener('keydown',onKey);return()=>document.removeEventListener('keydown',onKey);
 },[request]);
 function submit(e:React.FormEvent){e.preventDefault();if(!request)return;
  if(request.mode==='confirm'){close('yes');return}
  const clean=value.trim();const min=request.options.minimum??0,max=request.options.maximum??4000;
  if(clean.length<min){setError(`최소 ${min}자 이상 입력해 주세요.`);return}
  if(clean.length>max){setError(`최대 ${max}자까지 입력할 수 있습니다.`);return}
  if(request.options.numeric&&(!Number.isFinite(Number(clean))||Number(clean)<=0||!/^\d+$/.test(clean))){setError('올바른 양의 정수를 입력해 주세요.');return}
  close(clean);
 }
 const dialog=request?createPortal(<div className="action-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)close(null)}}>
  <div className="action-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descId} data-action-dialog>
   <form onSubmit={submit}>
    <h2 id={titleId}>{request.options.title}</h2>
    <p id={descId}>{request.options.description||'내용을 확인하고 다음 단계를 선택해 주세요.'}</p>
    {request.mode==='text'&&<label className="action-input-label">{request.options.inputLabel||'입력 내용'}<textarea ref={focusRef} className="input textarea" rows={request.options.numeric?2:4} value={value} onChange={e=>{setValue(e.target.value);setError('')}} maxLength={request.options.maximum??4000} /></label>}
    {error&&<p role="alert" className="action-error">{error}</p>}
    <div className="action-dialog-buttons"><button ref={cancelRef} type="button" className="btn outline" onClick={()=>close(null)}>돌아가기</button><button type="submit" className={'btn '+(request.options.danger?'danger':'primary')}>{request.options.confirmText||'확인'}</button></div>
   </form>
  </div>
 </div>,document.body):null;
 return {ask,confirm,dialog};
}
