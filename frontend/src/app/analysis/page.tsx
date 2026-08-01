import { AuthGuard } from "@/features/auth/components/AuthGuard";
import { InstrumentAnalysis } from "@/features/analysis/components/instrument-analysis";

export default function AnalysisPage() {
  return (
    <AuthGuard>
      <InstrumentAnalysis />
    </AuthGuard>
  );
}
