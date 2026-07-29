"use client";

import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "@/lib/api";

type Candidate = {rank:number;symbol:string;total_score:string;primary_setup?:string;matched_setups?:string[];average_trading_value_20?:string;atr_pct?:string;warnings:string[]};
const labels:Record<string,string>={box_breakout:"박스권 돌파",trend_pullback:"추세 눌림목",volatility_contraction_breakout:"변동성 축소 돌파"};
function compareDecimal(a:string,b:string) { const norm=(v:string)=>{const [i,f=""]=v.replace(/^\+/,"").split("."); return [i.replace(/^0+(?=\d)/,""),f.replace(/0+$/,"")] as const}; const [ai,af]=norm(a),[bi,bf]=norm(b); if(ai.length!==bi.length)return ai.length-bi.length; return ai.localeCompare(bi)||af.padEnd(Math.max(af.length,bf.length),"0").localeCompare(bf.padEnd(Math.max(af.length,bf.length),"0")); }
export function ScreenerDashboard(){
 const [items,setItems]=useState<Candidate[]>([]),[error,setError]=useState(""); const params=typeof window!=="undefined"?new URLSearchParams(window.location.search):new URLSearchParams();
 const [q,setQ]=useState(params.get("q")??""),[setup,setSetup]=useState(params.get("setup")??"");
 useEffect(()=>{apiRequest<Candidate[]>("/watchlist/latest").then(setItems).catch(()=>setError("스크리너 결과를 불러오지 못했습니다."));},[]);
 useEffect(()=>{const next=new URLSearchParams(window.location.search); q?next.set("q",q):next.delete("q"); setup?next.set("setup",setup):next.delete("setup"); history.replaceState(null,"",`${location.pathname}?${next}`)},[q,setup]);
 const shown=useMemo(()=>items.filter(x=>(!q||x.symbol.includes(q))&&(!setup||x.matched_setups?.includes(setup))).sort((a,b)=>a.rank-b.rank),[items,q,setup]);
 return <main><nav><a href="/dashboard">대시보드</a> · <strong>스크리너</strong></nav><h1>멀티 셋업 스윙 스크리너</h1><p>기술적 조건은 미래 수익을 보장하지 않으며 투자 자문이 아닙니다.</p>{error&&<p role="alert">{error}</p>}<label>종목 검색 <input value={q} onChange={e=>setQ(e.target.value)}/></label><label> 셋업 <select value={setup} onChange={e=>setSetup(e.target.value)}><option value="">전체</option>{Object.entries(labels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><table><thead><tr><th>순위</th><th>종목</th><th>점수</th><th>셋업</th><th>평균 거래대금</th><th>ATR</th></tr></thead><tbody>{shown.map(x=><tr key={x.symbol}><td>{x.rank}</td><td>{x.symbol}</td><td>{x.total_score}</td><td>{x.primary_setup?labels[x.primary_setup]:"-"}</td><td>{x.average_trading_value_20??"-"}</td><td>{x.atr_pct?`${x.atr_pct.replace(/^0\./,"").replace(/0+$/,"")}%`:"-"}</td></tr>)}</tbody></table><span hidden>{compareDecimal("1","1")}</span></main>
}
