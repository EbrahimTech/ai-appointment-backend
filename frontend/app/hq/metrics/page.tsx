"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Activity, AlertCircle, TrendingUp, DollarSign, MessageSquare, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

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
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading metrics...</p>
        </div>
      </div>
    );
  }

  if (metricsQuery.isError || !metricsQuery.data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Unable to load metrics.</p>
          <button
            type="button"
            onClick={() => metricsQuery.refetch()}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const metrics = metricsQuery.data.global;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header Section */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-center gap-4 mb-4">
            <Link
              href="/hq"
              className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Back to Tenants</span>
            </Link>
          </div>
          
          <div className="flex items-start gap-4">
            <div className="flex items-center justify-center w-16 h-16 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-lg">
              <BarChart3 className="w-8 h-8" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">Global Metrics</h1>
              <p className="text-sm text-gray-600">Operational performance across all clinics</p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Metrics Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <MetricCard
            label="TTFR p95"
            value={metrics.ttfr_p95_ms}
            unit="ms"
            icon={Activity}
            iconColor="text-blue-600"
            bgColor="bg-blue-50"
            description="Time to first response (95th percentile)"
          />
          <MetricCard
            label="Delivery Fail Rate"
            value={(metrics.delivery_fail_rate * 100).toFixed(2)}
            unit="%"
            icon={AlertCircle}
            iconColor="text-red-600"
            bgColor="bg-red-50"
            description="Failed message deliveries"
            isWarning={metrics.delivery_fail_rate > 0.05}
          />
          <MetricCard
            label="Handoff Rate"
            value={(metrics.handoff_rate * 100).toFixed(2)}
            unit="%"
            icon={MessageSquare}
            iconColor="text-amber-600"
            bgColor="bg-amber-50"
            description="Conversations requiring human intervention"
          />
          <MetricCard
            label="Grounded Answer Rate"
            value={(metrics.grounded_rate * 100).toFixed(2)}
            unit="%"
            icon={CheckCircle2}
            iconColor="text-green-600"
            bgColor="bg-green-50"
            description="Answers based on knowledge base"
            isGood={metrics.grounded_rate > 0.8}
          />
          <MetricCard
            label="LLM Cost Today"
            value={metrics.llm_cost_today.toFixed(2)}
            unit="$"
            icon={DollarSign}
            iconColor="text-purple-600"
            bgColor="bg-purple-50"
            description="Total LLM API costs for today"
          />
        </div>

        {/* Summary Section */}
        <div className="mt-8 bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Performance Summary</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex items-center gap-3 p-4 rounded-lg bg-gray-50">
              <TrendingUp className="w-5 h-5 text-gray-600" />
              <div>
                <p className="text-sm font-medium text-gray-900">Overall Health</p>
                <p className="text-xs text-gray-600">
                  {metrics.delivery_fail_rate < 0.05 && metrics.grounded_rate > 0.7
                    ? "System operating normally"
                    : "Some metrics need attention"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-4 rounded-lg bg-gray-50">
              <Activity className="w-5 h-5 text-gray-600" />
              <div>
                <p className="text-sm font-medium text-gray-900">Response Time</p>
                <p className="text-xs text-gray-600">
                  {metrics.ttfr_p95_ms < 2000 ? "Excellent" : metrics.ttfr_p95_ms < 5000 ? "Good" : "Needs improvement"}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCard({
  label,
  value,
  unit,
  icon: Icon,
  iconColor,
  bgColor,
  description,
  isWarning,
  isGood,
}: {
  label: string;
  value: number | string;
  unit?: string;
  icon: React.ComponentType<{ className?: string }>;
  iconColor: string;
  bgColor: string;
  description?: string;
  isWarning?: boolean;
  isGood?: boolean;
}) {
  const borderColor = isWarning ? "border-red-200" : isGood ? "border-green-200" : "border-gray-200";
  const shadowColor = isWarning ? "shadow-red-50" : isGood ? "shadow-green-50" : "";

  return (
    <div className={`bg-white rounded-xl border ${borderColor} p-6 shadow-sm hover:shadow-md transition-all ${shadowColor}`}>
      <div className="flex items-start justify-between mb-4">
        <div className={`flex items-center justify-center w-12 h-12 rounded-lg ${bgColor}`}>
          <Icon className={`w-6 h-6 ${iconColor}`} />
        </div>
        {(isWarning || isGood) && (
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
              isWarning ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700"
            }`}
          >
            {isWarning ? "Warning" : "Good"}
          </span>
        )}
      </div>
      <div className="mb-2">
        <p className="text-sm font-medium text-gray-600 mb-1">{label}</p>
        <div className="flex items-baseline gap-1">
          <p className="text-3xl font-bold text-gray-900">{value}</p>
          {unit && <p className="text-lg font-semibold text-gray-600">{unit}</p>}
        </div>
      </div>
      {description && <p className="text-xs text-gray-500 mt-2">{description}</p>}
    </div>
  );
}
