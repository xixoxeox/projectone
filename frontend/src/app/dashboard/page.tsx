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
          <Link href="/backtests">백테스트</Link>
          {" · "}<Link href="/screener">스크리너</Link>
        </nav>
        <header>
          <p className="eyebrow">SWING SCREENER</p>
          <h1>대시보드</h1>
        </header>
        <section className="card">
          <h2>프로젝트 준비 완료</h2>
          <p className="muted">
            시장 데이터와 스크리닝 기능은 다음 스프린트에서 제공됩니다.
          </p>
        </section>
      </main>
    </AuthGuard>
  );
}
