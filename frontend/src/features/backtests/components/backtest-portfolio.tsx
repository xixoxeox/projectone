import { useEffect, useState } from "react";
import { BacktestApiError, getBacktestPortfolio } from "../api";
import { money, percent } from "../format";
import type { PortfolioResult } from "../types";

const summaries: Array<[keyof PortfolioResult,string,"money"|"percent"|"plain"]> = [
  ["initial_capital","초기 자본","money"],["final_equity","최종 자산","money"],["final_cash","최종 현금","money"],
  ["net_profit","순이익","money"],["total_return","총수익률","percent"],["max_drawdown","최대 낙폭","money"],
  ["max_drawdown_pct","최대 낙폭 비율","percent"],["maximum_open_positions_used","최대 동시 보유 수","plain"],
  ["average_capital_utilization","평균 자본 사용률","percent"],
];
function finite(value:string){const number=Number(value);return Number.isFinite(number)?number:0}
function Spark({data,label,keys}:{data:PortfolioResult["snapshots"];label:string;keys:Array<"total_equity"|"cash"|"market_value"|"drawdown"|"drawdown_pct">}){
 const values=data.flatMap(row=>keys.map(key=>finite(row[key]))), max=Math.max(...values,1), min=Math.min(...values,0), range=max-min||1;
 return <figure><figcaption>{label}</figcaption><svg viewBox="0 0 600 180" role="img" aria-label={`${label}: ${data.map(row=>`${row.trading_date} ${keys.map(key=>`${key} ${row[key]}`).join(", ")}`).join("; ")}`}>
 {keys.map((key,index)=><polyline key={key} fill="none" stroke={["#2563eb","#16a34a","#ea580c"][index]} strokeWidth="2" points={data.map((row,i)=>`${data.length<2?0:i*600/(data.length-1)},${170-(finite(row[key])-min)*160/range}`).join(" ")}/>)}</svg></figure>
}
export function BacktestPortfolio({runId}:{runId:string}){
 const [data,setData]=useState<PortfolioResult|null>(null),[error,setError]=useState(""),[retry,setRetry]=useState(0);
 useEffect(()=>{let active=true;setData(null);setError("");getBacktestPortfolio(runId).then(value=>{if(active)setData(value)}).catch(err=>{if(active)setError(err instanceof BacktestApiError?err.message:"포트폴리오 데이터를 불러오지 못했습니다.")});return()=>{active=false}},[runId,retry]);
 if(error)return <section className="panel" role="alert"><p>{error}</p><button onClick={()=>setRetry(x=>x+1)}>다시 시도</button></section>;
 if(!data)return <section className="panel" aria-busy="true">포트폴리오 데이터를 불러오는 중…</section>;
 return <section className="panel"><h2>포트폴리오 분석</h2><dl className="metric-grid">{summaries.map(([key,label,kind])=><div key={key}><dt>{label}</dt><dd>{kind==="money"?money(String(data[key])):kind==="percent"?percent(String(data[key])):String(data[key])}</dd></div>)}</dl>
 {data.snapshots.length===0?<p>일별 스냅샷이 없습니다.</p>:<><Spark data={data.snapshots} label="일별 포트폴리오 자산" keys={["total_equity","cash","market_value"]}/><Spark data={data.snapshots} label="포트폴리오 낙폭" keys={["drawdown","drawdown_pct"]}/><h3>자본 사용률</h3><p>{percent(data.average_capital_utilization)}</p><div className="table-scroll"><table><caption>일별 포트폴리오 스냅샷</caption><thead><tr>{["날짜","현금","시장 가치","실현 손익","미실현 손익","총자산","누적 수익률","낙폭","낙폭 비율","보유 수"].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{data.snapshots.map(row=><tr key={row.trading_date}><td>{row.trading_date}</td><td>{row.cash}</td><td>{row.market_value}</td><td>{row.realized_pnl}</td><td>{row.unrealized_pnl}</td><td>{row.total_equity}</td><td>{row.cumulative_return}</td><td>{row.drawdown}</td><td>{row.drawdown_pct}</td><td>{row.open_position_count}</td></tr>)}</tbody></table></div></>}</section>
}
