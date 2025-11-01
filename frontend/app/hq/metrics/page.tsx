"use client";

import { useQuery } from "@tanstack/react-query";

type MetricsResponse = {
  global: {
    ttfr_p95_ms: number;
    delivery_fail_rate: number;
    handoff_rate: number;
    grounded_rate: number;
    llm_cost_today: number;
  };
};

export default function HQMetricsPage() {
  const metricsQuery = useQuery({
    queryKey: ["hqMetricsSummary"],
    queryFn: async () => {
      const response = await fetch("/api/proxy/hq/metrics/summary");
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load metrics");
      }
      return payload.data as MetricsResponse;
    },
  });

  if (metricsQuery.isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading metrics...</p>
      </main>
    );
  }

  if (metricsQuery.isError || !metricsQuery.data) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Unable to load metrics.</p>
          <button
            type="button"
            onClick={() => metricsQuery.refetch()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  const metrics = metricsQuery.data.global;

  return (
    <main className="space-y-8 px-6 py-8">
      <header>
        <h1 className="text-2xl font-semibold">Global Metrics</h1>
        <p className="text-sm text-muted-foreground">Operational performance across all clinics.</p>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <MetricCard label="TTFR p95 (ms)" value={metrics.ttfr_p95_ms} />
        <MetricCard label="Delivery fail rate" value={`${(metrics.delivery_fail_rate * 100).toFixed(2)}%`} />
        <MetricCard label="Handoff rate" value={`${(metrics.handoff_rate * 100).toFixed(2)}%`} />
        <MetricCard label="Grounded answer rate" value={`${(metrics.grounded_rate * 100).toFixed(2)}%`} />
        <MetricCard label="LLM cost today" value={`$${metrics.llm_cost_today.toFixed(2)}`} />
      </section>
    </main>
  );
}

function MetricCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </div>
  );
}
