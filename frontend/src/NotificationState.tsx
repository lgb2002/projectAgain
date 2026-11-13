import React,{createContext,useCallback,useContext,useEffect,useRef,useState} from 'react';
import {api,body} from './api';

export type NoticeItem={id:string;title:string;kind:string;resource_type:string;resource_id:string;created_at:string;read_at:string|null};
type State={items:NoticeItem[];unread:number;hasMore:boolean;loading:boolean;loadingMore:boolean;error:string;refresh:()=>Promise<void>;loadMore:()=>Promise<void>;mark:(id:string)=>Promise<boolean>;markAll:()=>Promise<boolean>};
const Context=createContext<State|null>(null);
export function useNotifications(){const value=useContext(Context);if(!value)throw new Error('NotificationProvider is required');return value}
export function NotificationProvider({userId,children}:{userId:string|null;children:React.ReactNode}){
 const [items,setItems]=useState<NoticeItem[]>([]),[unread,setUnread]=useState(0),[hasMore,setHasMore]=useState(false),[loading,setLoading]=useState(false),[loadingMore,setLoadingMore]=useState(false),[error,setError]=useState('');
 const revision=useRef(0),request=useRef(0),pending=useRef(new Set<string>());
 const refresh=useCallback(async()=>{
  if(!userId){setItems([]);setUnread(0);return}
  const snapshot=revision.current,seq=++request.current;
  setLoading(true);
  try{const data=await api<{items:NoticeItem[];unread:number;has_more:boolean}>('/notifications?limit=100&offset=0');
   if(snapshot===revision.current&&seq===request.current){setItems(old=>{const ids=new Set(data.items.map(x=>x.id));return [...data.items,...old.filter(x=>!ids.has(x.id))]});setUnread(data.unread);setHasMore(data.has_more);setError('')}
  }catch(e){if(seq===request.current)setError(e instanceof Error?e.message:'알림을 불러오지 못했습니다.')}
  finally{if(seq===request.current)setLoading(false)}
 },[userId]);
 useEffect(()=>{revision.current++;request.current++;setItems([]);setUnread(0);setHasMore(false);setError('');if(!userId)return;
  void refresh();const timer=window.setInterval(()=>{void refresh()},45000);
  const onFocus=()=>{void refresh()};const onVisible=()=>{if(document.visibilityState==='visible')void refresh()};
  window.addEventListener('focus',onFocus);document.addEventListener('visibilitychange',onVisible);
  return()=>{window.clearInterval(timer);window.removeEventListener('focus',onFocus);document.removeEventListener('visibilitychange',onVisible);revision.current++;request.current++};
 },[userId,refresh]);
 const loadMore=useCallback(async()=>{
  if(!userId||loadingMore||!hasMore)return;
  const snapshot=revision.current;setLoadingMore(true);
  try{const data=await api<{items:NoticeItem[];unread:number;has_more:boolean}>(`/notifications?limit=100&offset=${items.length}`);
   if(snapshot!==revision.current)return;
   setItems(prev=>{const seen=new Set(prev.map(n=>n.id));return [...prev,...data.items.filter(x=>!seen.has(x.id))]});
   setHasMore(data.has_more);setUnread(data.unread);setError('');
  }catch(e){setError(e instanceof Error?e.message:'추가 알림을 불러오지 못했습니다.')}
  finally{setLoadingMore(false)}
 },[userId,loadingMore,hasMore,items.length]);
 const mark=useCallback(async(id:string)=>{
  if(pending.current.has(id))return false;pending.current.add(id);
  try{await api(`/notifications/${id}/read`,body({}));revision.current++;request.current++;
   setItems(prev=>prev.map(n=>n.id===id?{...n,read_at:n.read_at||new Date().toISOString()}:n));
   setUnread(prev=>Math.max(0,prev-(items.some(n=>n.id===id&&!n.read_at)?1:0)));setError('');void refresh();return true;
  }catch(e){setError(e instanceof Error?e.message:'읽음 처리에 실패했습니다.');void refresh();return false}
  finally{pending.current.delete(id)}
 },[items,refresh]);
 const markAll=useCallback(async()=>{
  try{await api('/notifications/read-all',body({}));revision.current++;request.current++;
   setItems(prev=>prev.map(n=>({...n,read_at:n.read_at||new Date().toISOString()})));setUnread(0);setError('');void refresh();return true;
  }catch(e){setError(e instanceof Error?e.message:'모두 읽음 처리에 실패했습니다.');void refresh();return false}
 },[refresh]);
 return <Context.Provider value={{items,unread,hasMore,loading,loadingMore,error,refresh,loadMore,mark,markAll}}>{children}</Context.Provider>
}
