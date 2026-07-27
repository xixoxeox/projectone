"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
export default function LoginPage() { const router=useRouter(); const [error,setError]=useState(""); const [busy,setBusy]=useState(false);
async function submit(event:FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); setError(""); const data=new FormData(event.currentTarget); try { await login(String(data.get("username")), String(data.get("password"))); router.replace("/dashboard"); } catch(e) { setError(e instanceof Error ? e.message : "로그인에 실패했습니다."); setBusy(false); } }
return <main className="center"><section className="card"><p className="eyebrow">SWING SCREENER</p><h1>관리자 로그인</h1><p className="muted">시장 의사결정 지원 대시보드에 접속하세요.</p><form onSubmit={submit}><label>아이디<input name="username" autoComplete="username" required /></label><label>비밀번호<input name="password" type="password" autoComplete="current-password" minLength={8} required /></label>{error && <p role="alert" className="error">{error}</p>}<button disabled={busy}>{busy ? "로그인 중…" : "로그인"}</button></form></section></main>; }
