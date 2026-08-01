"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getWatchlistDetail, WatchlistApiError } from "../api";
import { formatDecimal } from "../format";
import type { WatchlistDetail as Detail } from "../types";
import { WatchlistEmpty, WatchlistError, WatchlistLoading } from "./states";

export function WatchlistDetail({ tradingDate, symbol }: { tradingDate: string; symbol: string }) {
  const [detail, setDetail] = useState<Detail | null>(null); const [status, setStatus] = useState<"loading"|"ready"|"not-found"|"error">("loading"); const [attempt, setAttempt] = useState(0);
  const load = useCallback(async () => { void attempt; setStatus("loading"); try { setDetail(await getWatchlistDetail(tradingDate, symbol)); setStatus("ready"); } catch (error) { setStatus(error instanceof WatchlistApiError && error.status === 404 ? "not-found" : "error"); } }, [tradingDate, symbol, attempt]);
  useEffect(() => { void load(); }, [load]);
  if (status === "loading") return <main className="watchlist-shell"><WatchlistLoading/></main>;
  if (status === "not-found") return <main className="watchlist-shell"><WatchlistEmpty notFound/></main>;
  if (status === "error" || !detail) return <main className="watchlist-shell"><WatchlistError onRetry={() => setAttempt(v => v + 1)}/></main>;
  return <main className="watchlist-shell detail"><Link className="back-link" href={`/watchlist?date=${encodeURIComponent(tradingDate)}`}>← 목록으로</Link><header className="detail-hero"><p>{detail.trading_date}</p><div><span className="detail-rank">#{detail.rank}</span><h1>{detail.symbol}</h1></div><p className="detail-score"><span>종합 점수</span>{formatDecimal(detail.total_score)}</p><Link className="back-link" href={`/analysis?symbol=${encodeURIComponent(detail.symbol)}`}>최신 차트로 실시간 분석 →</Link></header>
    {(detail.screener_name || detail.screener_version) && <p>{detail.screener_name ?? "스크리너"} v{detail.screener_version ?? "—"}</p>}
    {detail.primary_setup && <p>대표 셋업: {detail.primary_setup}</p>}
    {detail.matched_setups?.length ? <p>일치 셋업: {detail.matched_setups.join(", ")}</p> : null}
    <section className="detail-section" aria-labelledby="components-heading"><h2 id="components-heading">구성 점수</h2><dl className="detail-grid">{Object.entries(detail.component_scores).map(([key,value]) => <div key={key}><dt>{key}</dt><dd>{formatDecimal(value)}</dd></div>)}</dl></section>
    <AuditMap title="셋업 점수" values={detail.setup_scores}/>
    <AuditMap title="설정 스냅샷" values={detail.configuration_snapshot}/>
    {Object.entries(detail.setup_metrics ?? {}).map(([setup, values]) => <AuditMap key={setup} title={`셋업 지표: ${setup}`} values={values}/>)}
    {Object.entries(groupRules(detail.rule_evaluations ?? {})).map(([setup, values]) => <AuditMap key={setup} title={`규칙 평가: ${setup}`} values={values}/>)}
    <WarningSection title="랭킹 경고" warnings={detail.warnings} className="ranking-warnings"/>
    <section className="detail-section" aria-labelledby="screen-heading"><h2 id="screen-heading">스크리닝 결과</h2><p className={`pass-badge ${detail.snapshot.passed ? "passed" : "failed"}`}>{detail.snapshot.passed ? "통과" : "미통과"}</p></section>
    <section className="detail-section" aria-labelledby="metrics-heading"><h2 id="metrics-heading">지표</h2><dl className="detail-grid">{Object.entries(detail.metrics).map(([key,value]) => <div key={key}><dt>{key}</dt><dd>{formatDecimal(value)}</dd></div>)}</dl>{Object.keys(detail.metrics).length === 0 && <p className="muted">표시할 지표가 없습니다.</p>}</section>
    <section className="detail-section" aria-labelledby="reasons-heading"><h2 id="reasons-heading">판단 근거</h2>{detail.reasons.length ? <ul className="reason-list">{detail.reasons.map((reason,i) => <li key={`${reason}-${i}`}>{reason}</li>)}</ul> : <p className="muted">등록된 판단 근거가 없습니다.</p>}</section>
    <WarningSection title="스크리닝 경고" warnings={detail.snapshot.warnings} className="screening-warnings"/>
    <p className="muted">기술적 후보는 미래 수익을 보장하지 않으며 투자 자문이 아닙니다.</p>
  </main>;
}
function groupRules(rules:Record<string,boolean>):Record<string,Record<string,boolean>> { return Object.entries(rules).reduce<Record<string,Record<string,boolean>>>((groups,[key,value])=>{const [setup,rule]=key.split(":",2);(groups[setup]??={})[rule??key]=value;return groups},{}); }
function AuditMap({title,values}:{title:string;values?:Record<string,string|number|boolean>}) { if(!values||Object.keys(values).length===0)return null;return <section className="detail-section"><h2>{title}</h2><dl className="detail-grid">{Object.entries(values).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{typeof value==="string"?formatDecimal(value):String(value)}</dd></div>)}</dl></section>; }
function WarningSection({title,warnings,className}:{title:string;warnings:string[];className:string}) { return <section className={`detail-section ${className}`} aria-labelledby={`${className}-heading`}><h2 id={`${className}-heading`}>{title}</h2>{warnings.length ? <ul className="warning-list">{warnings.map((warning,i) => <li key={`${warning}-${i}`}>⚠ {warning}</li>)}</ul> : <p className="warning-clear">✓ 경고 없음</p>}</section>; }
