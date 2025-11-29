"use client";

import { useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  MessageSquare,
  Calendar,
  Activity,
  AlertCircle,
  TrendingUp,
  RefreshCw,
  CheckCircle2,
  XCircle,
} from "lucide-react";

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
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-4">
          <div className="flex items-center justify-center w-16 h-16 rounded-full bg-red-100 mx-auto">
            <XCircle className="w-8 h-8 text-red-600" />
          </div>
          <div>
            <p className="text-base font-medium text-gray-900 mb-1">Unable to load dashboard</p>
            <p className="text-sm text-gray-500 mb-4">Please try again</p>
          </div>
          <button
            type="button"
            onClick={() => dashboardQuery.refetch()}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            <span>Retry</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header Section */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6 py-6">
      <div className="flex items-start justify-between">
            <div className="flex items-start gap-4">
              <div className="flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg">
                <Activity className="w-7 h-7" />
              </div>
        <div>
                <h1 className="text-3xl font-bold text-gray-900 mb-2 capitalize">{slug} Dashboard</h1>
                <p className="text-sm text-gray-600">Daily performance snapshot and key metrics</p>
              </div>
        </div>
        <button
          type="button"
          onClick={() => dashboardQuery.refetch()}
              disabled={dashboardQuery.isFetching}
              className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors shadow-sm"
        >
              <RefreshCw className={`w-4 h-4 ${dashboardQuery.isFetching ? "animate-spin" : ""}`} />
              <span>Refresh</span>
        </button>
          </div>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <MetricCard
            title="Conversations Today"
            value={data.conversations_today}
            icon={MessageSquare}
            iconColor="text-blue-600"
            bgColor="bg-blue-50"
            description="Total conversations started"
          />
          <MetricCard
            title="Bookings Today"
            value={data.bookings_today}
            icon={Calendar}
            iconColor="text-green-600"
            bgColor="bg-green-50"
            description="Appointments scheduled"
          />
          <MetricCard
            title="TTFR p95"
            value={`${data.ttfr_p95_ms}ms`}
            icon={Activity}
            iconColor="text-purple-600"
            bgColor="bg-purple-50"
            description="Time to first response (95th percentile)"
          />
          <MetricCard
            title="Handoff Today"
            value={data.handoff_today}
            icon={AlertCircle}
            iconColor="text-amber-600"
            bgColor="bg-amber-50"
            description="Conversations requiring human intervention"
          />
          <MetricCard
            title="Delivery Fail Rate"
            value={`${(data.delivery_fail_rate * 100).toFixed(1)}%`}
            icon={TrendingUp}
            iconColor="text-red-600"
            bgColor="bg-red-50"
            description="Failed message deliveries"
            isWarning={data.delivery_fail_rate > 0.05}
          />
          {typeof data.tentative_today === "number" && (
            <MetricCard
              title="Tentative Syncs"
              value={data.tentative_today}
              icon={RefreshCw}
              iconColor="text-indigo-600"
              bgColor="bg-indigo-50"
              description="Pending calendar synchronizations"
              badge={data.tentative_today > 0 ? { text: "Action needed", variant: "warning" } : undefined}
          />
          )}
          {typeof data.failed_count === "number" && (
            <MetricCard
              title="Failed Syncs"
              value={data.failed_count}
              icon={XCircle}
              iconColor="text-red-600"
              bgColor="bg-red-50"
              description="Total failed synchronizations"
              badge={data.failed_count > 0 ? { text: "Investigate", variant: "destructive" } : undefined}
            />
          )}
              </div>
      </div>
    </div>
  );
}

function MetricCard({
  title,
  value,
  icon: Icon,
  iconColor,
  bgColor,
  description,
  isWarning,
  badge,
}: {
  title: string;
  value: number | string;
  icon: React.ComponentType<{ className?: string }>;
  iconColor: string;
  bgColor: string;
  description?: string;
  isWarning?: boolean;
  badge?: { text: string; variant: "warning" | "destructive" };
}) {
  return (
    <div className={`bg-white rounded-xl border ${isWarning ? "border-red-200" : "border-gray-200"} p-6 shadow-sm hover:shadow-md transition-all`}>
      <div className="flex items-start justify-between mb-4">
        <div className={`flex items-center justify-center w-12 h-12 rounded-lg ${bgColor}`}>
          <Icon className={`w-6 h-6 ${iconColor}`} />
        </div>
        {badge && (
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
              badge.variant === "warning" ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"
            }`}
          >
            {badge.text}
          </span>
        )}
      </div>
      <div className="mb-2">
        <p className="text-sm font-medium text-gray-600 mb-1">{title}</p>
        <div className="text-3xl font-bold text-gray-900">{value}</div>
      </div>
      {description && <p className="text-xs text-gray-500 mt-2">{description}</p>}
    </div>
  );
}
