import { AuthGuard } from "@/features/auth/components/AuthGuard";
import Link from "next/link";
export default function Dashboard() {
  return (
    <AuthGuard>
      <main className="shell">
        <nav aria-label="주요 메뉴">
          <Link aria-current="page" href="/dashboard">
            대시보드
          </Link>{" "}
          · <Link href="/watchlist">관심 종목</Link> ·{" "}
          <Link href="/analysis">종목 분석</Link> ·{" "}
          <Link href="/backtests">백테스트</Link> · <Link href="/screener">스크리너</Link>
        </nav>
        <header>
          <p className="eyebrow">SWING SCREENER</p>
          <h1>대시보드</h1>
        </header>
        <section className="card">
          <h2>스윙 트레이딩 의사결정 도구</h2>
          <p className="muted">
            스크리너로 핵심 후보를 찾거나 종목 분석에서 궁금한 종목을 바로 확인하세요.
          </p>
        </section>
      </main>
    </AuthGuard>
  );
}
