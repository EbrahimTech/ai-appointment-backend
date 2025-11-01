"use client";

import { useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

type DashboardData = {
  conversations_today: number;
  bookings_today: number;
  ttfr_p95_ms: number;
  handoff_today: number;
  delivery_fail_rate: number;
  tentative_today?: number;
  failed_count?: number;
};

export default function ClinicDashboardPage() {
  const params = useParams<{ slug: string }>();
  const router = useRouter();
  const slug = params.slug;

  const dashboardQuery = useQuery({
    queryKey: ["clinicDashboard", slug],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/dashboard`);
      if (response.status === 403 || response.status === 401) {
        router.replace("/select-clinic");
        return null;
      }
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "LOAD_FAILED");
      }
      return payload.data as DashboardData;
    },
  });

  const data = useMemo(() => dashboardQuery.data, [dashboardQuery.data]);

  if (dashboardQuery.isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading dashboard...</p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Unable to load dashboard metrics.</p>
          <button
            type="button"
            onClick={() => dashboardQuery.refetch()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="px-6 py-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold capitalize">{slug} dashboard</h1>
          <p className="text-sm text-muted-foreground">Daily performance snapshot.</p>
        </div>
        <button
          type="button"
          onClick={() => dashboardQuery.refetch()}
          className="rounded-md border px-3 py-1 text-sm"
        >
          Refresh
        </button>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-3">
        <Card title="Conversations today" value={data.conversations_today} />
        <Card title="Bookings today" value={data.bookings_today} />
        <Card title="TTFR p95 (ms)" value={data.ttfr_p95_ms} />
        <Card title="Handoff today" value={data.handoff_today} />
        <Card title="Delivery fail rate" value={`${(data.delivery_fail_rate * 100).toFixed(1)}%`} />
        {typeof data.tentative_today === "number" ? (
          <Card
            title="Tentative syncs today"
            value={
              <div className="flex items-center gap-2">
                <span>{data.tentative_today}</span>
                {data.tentative_today > 0 ? <Badge variant="warning">Action needed</Badge> : null}
              </div>
            }
          />
        ) : null}
        {typeof data.failed_count === "number" ? (
          <Card
            title="Failed syncs total"
            value={
              <div className="flex items-center gap-2">
                <span>{data.failed_count}</span>
                {data.failed_count > 0 ? <Badge variant="destructive">Investigate</Badge> : null}
              </div>
            }
          />
        ) : null}
      </div>
    </main>
  );
}

function Card({ title, value }: { title: string; value: number | string | JSX.Element }) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <p className="text-sm text-muted-foreground">{title}</p>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  );
}

function Badge({ variant = "default", children }: { variant?: "default" | "warning" | "destructive"; children: React.ReactNode }) {
  const styles: Record<typeof variant, string> = {
    default: "bg-slate-100 text-slate-600",
    warning: "bg-amber-100 text-amber-700",
    destructive: "bg-red-100 text-red-700",
  };
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[variant]}`}>{children}</span>;
}
