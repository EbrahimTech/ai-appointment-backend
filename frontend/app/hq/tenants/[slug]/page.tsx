
"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { ArrowLeft, Building2, MessageSquare, Calendar, Activity, Shield } from "lucide-react";
import Link from "next/link";

type TenantItem = {
  clinic: {
    id: number;
    slug: string;
    name: string;
  };
  channels_status: string;
  calendar_status: string;
  last_ttfr_p95_ms: number;
};

type WhatsAppStatus = {
  status: "OK" | "WARN" | "DOWN";
  last_success_at: string | null;
  last_error_at: string | null;
  provider: string | null;
};

type GoogleStatus = {
  status: "OK" | "WARN" | "DISCONNECTED";
  last_auth_at: string | null;
  last_error: string | null;
};

export default function TenantDetailPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const { support, setSupport, clearSupport } = useSupportSession();
  const [reason, setReason] = useState("Investigate issue");
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const tenantsQuery = useQuery({
    queryKey: ["hqTenants"],
    queryFn: async () => {
      const response = await fetch("/api/proxy/hq/tenants");
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load tenants");
      }
      return payload;
    },
  });

  const whatsappQuery = useQuery({
    queryKey: ["tenantWhatsapp", slug],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/channels/whatsapp`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load WhatsApp status");
      }
      return payload.data as WhatsAppStatus;
    },
  });

  const googleQuery = useQuery({
    queryKey: ["tenantGoogle", slug],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/calendar/google`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load Google status");
      }
      return payload.data as GoogleStatus;
    },
  });

  const startSupport = useMutation({
    mutationFn: async ({ clinic_id }: { clinic_id: number }) => {
      const response = await fetch("/api/support/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clinic_id, reason, clinic_slug: slug }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to start support session");
      }
      return payload.data as { support_token: string; expires_at: string };
    },
    onSuccess: (data) => {
      setSupport({ token: data.support_token, clinicSlug: slug, expiresAt: data.expires_at ?? null });
      setFeedback(`Impersonation started. Session expires at ${new Date(data.expires_at).toLocaleString()}.`);
      setError(null);
    },
    onError: (err: Error) => {
      setError(err.message);
      setFeedback(null);
    },
  });

  const stopSupport = useMutation({
    mutationFn: async () => {
      const response = await fetch("/api/support/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const payload = await response.json();
      if (!response.ok || payload?.ok === false) {
        throw new Error(payload.error || "Failed to stop support session");
      }
      return payload;
    },
    onSuccess: () => {
      clearSupport();
      setFeedback("Impersonation stopped.");
      setError(null);
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  // All hooks must be called before any early returns
  const tenants = useMemo(() => {
    if (!tenantsQuery.data) return [];
    const items = tenantsQuery.data?.data?.items;
    if (!items) return [];
    return Array.isArray(items) ? items : [];
  }, [tenantsQuery.data]);
  const tenant = Array.isArray(tenants) ? tenants.find((item) => item.clinic.slug === slug) : undefined;

  if (tenantsQuery.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading tenant details...</p>
        </div>
      </div>
    );
  }

  if (tenantsQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Unable to load tenant details.</p>
          <button
            type="button"
            onClick={() => tenantsQuery.refetch()}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }
  if (!tenant) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Tenant not found.</p>
          <Link
            href="/hq"
            className="inline-block rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Back to Tenants
          </Link>
        </div>
      </div>
    );
  }

  const isImpersonating = support?.clinicSlug === slug;

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
          
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-4">
              <div className="flex items-center justify-center w-16 h-16 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-lg">
                <Building2 className="w-8 h-8" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900 mb-2">{tenant.clinic.name}</h1>
                <div className="flex items-center gap-4 text-sm text-gray-600">
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium">Slug:</span>
                    <code className="px-2 py-0.5 bg-gray-100 rounded text-gray-800 font-mono">{tenant.clinic.slug}</code>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium">ID:</span>
                    <span className="px-2 py-0.5 bg-gray-100 rounded">{tenant.clinic.id}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Alerts */}
        {feedback ? <Alert variant="success" message={feedback} /> : null}
        {error ? <Alert variant="error" message={error} /> : null}

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-gray-600">
                <Activity className="w-5 h-5" />
                <span className="text-sm font-medium">TTFR p95</span>
              </div>
            </div>
            <div className="text-2xl font-bold text-gray-900">{tenant.last_ttfr_p95_ms}ms</div>
            <p className="text-xs text-gray-500 mt-1">Last 7 days</p>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-gray-600">
                <MessageSquare className="w-5 h-5" />
                <span className="text-sm font-medium">Channels</span>
              </div>
            </div>
            <div className="mt-2">
              <StatusBadge status={tenant.channels_status} />
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2 text-gray-600">
                <Calendar className="w-5 h-5" />
                <span className="text-sm font-medium">Calendar</span>
              </div>
            </div>
            <div className="mt-2">
              <StatusBadge status={tenant.calendar_status} />
            </div>
          </div>
        </div>

        {/* Integration Cards */}
        <div className="grid gap-6 md:grid-cols-2 mb-6">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
            <div className="bg-gradient-to-r from-green-50 to-emerald-50 border-b border-gray-200 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-green-100">
                  <MessageSquare className="w-5 h-5 text-green-600" />
                </div>
                <h2 className="text-lg font-semibold text-gray-900">WhatsApp Channel</h2>
              </div>
            </div>
            <div className="p-6">
              {whatsappQuery.isPending ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                  <span className="ml-3 text-sm text-gray-600">Loading status...</span>
                </div>
              ) : whatsappQuery.isError ? (
                <div className="text-center py-8">
                  <p className="text-sm text-red-600">Unable to load WhatsApp status.</p>
                </div>
              ) : (
                <StatusCard
                  title="WhatsApp"
                  status={whatsappQuery.data?.status ?? "DOWN"}
                  details={[
                    { label: "Provider", value: whatsappQuery.data?.provider ?? "—", icon: "provider" },
                    { label: "Last success", value: whatsappQuery.data?.last_success_at ? new Date(whatsappQuery.data.last_success_at).toLocaleString() : "—", icon: "success" },
                    { label: "Last error", value: whatsappQuery.data?.last_error_at ? new Date(whatsappQuery.data.last_error_at).toLocaleString() : "—", icon: "error" },
                  ]}
                />
              )}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
            <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-gray-200 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-blue-100">
                  <Calendar className="w-5 h-5 text-blue-600" />
                </div>
                <h2 className="text-lg font-semibold text-gray-900">Google Calendar</h2>
              </div>
            </div>
            <div className="p-6">
              {googleQuery.isPending ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                  <span className="ml-3 text-sm text-gray-600">Loading status...</span>
                </div>
              ) : googleQuery.isError ? (
                <div className="text-center py-8">
                  <p className="text-sm text-red-600">Unable to load Google status.</p>
                </div>
              ) : (
                <StatusCard
                  title="Google Calendar"
                  status={googleQuery.data?.status ?? "DISCONNECTED"}
                  details={[
                    { label: "Last auth", value: googleQuery.data?.last_auth_at ? new Date(googleQuery.data.last_auth_at).toLocaleString() : "—", icon: "auth" },
                    { label: "Last error", value: googleQuery.data?.last_error ?? "—", icon: "error" },
                  ]}
                />
              )}
            </div>
          </div>
        </div>

        {/* Support Session Section */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-purple-100">
              <Shield className="w-5 h-5 text-purple-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Support Session</h2>
              <p className="text-sm text-gray-600">Impersonate this clinic for support purposes</p>
            </div>
          </div>
          
          {isImpersonating ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 mb-4">
              <p className="text-sm text-amber-900 mb-3">
                <strong>Active session:</strong> You are currently impersonating this clinic. Read-only actions only (template replies allowed).
              </p>
              <button
                type="button"
                onClick={() => stopSupport.mutate()}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                disabled={stopSupport.isPending}
              >
                {stopSupport.isPending ? "Stopping..." : "Stop Impersonation"}
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <label htmlFor="reason" className="block text-sm font-medium text-gray-700 mb-2">
                  Reason for impersonation
                </label>
                <textarea
                  id="reason"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  rows={3}
                  className="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                  placeholder="e.g., Investigate customer complaint, debug integration issue..."
                />
              </div>
              <button
                type="button"
                onClick={() => startSupport.mutate({ clinic_id: tenant.clinic.id })}
                className="rounded-md bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
                disabled={startSupport.isPending || !reason.trim()}
              >
                {startSupport.isPending ? "Starting..." : "Start Impersonation"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Alert({ variant, message }: { variant: "success" | "error"; message: string }) {
  const styles =
    variant === "success"
      ? "border-green-200 bg-green-50 text-green-700"
      : "border-red-200 bg-red-50 text-red-700";
  return <div className={`rounded-lg border px-4 py-3 text-sm mb-6 ${styles}`}>{message}</div>;
}

function StatusCard({
  title,
  status,
  details,
}: {
  title: string;
  status: string;
  details: { label: string; value: string; icon?: string }[];
}) {
  return (
    <div>
      <div className="mb-4">
        <StatusBadge status={status} size="large" />
      </div>
      <dl className="space-y-3">
        {details.map((detail) => (
          <div key={detail.label} className="flex items-start justify-between gap-4 pb-3 border-b border-gray-100 last:border-0">
            <dt className="text-sm font-medium text-gray-600">{detail.label}</dt>
            <dd className="text-sm text-right text-gray-900 font-mono max-w-[60%] break-words">
              {detail.value || "—"}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function StatusBadge({ status, size = "default" }: { status: string; size?: "default" | "large" }) {
  const statusConfig: Record<string, { bg: string; text: string; border: string; dot: string; label: string }> = {
    OK: {
      bg: "bg-green-50",
      text: "text-green-700",
      border: "border-green-200",
      dot: "bg-green-500",
      label: "Operational",
    },
    WARN: {
      bg: "bg-yellow-50",
      text: "text-yellow-700",
      border: "border-yellow-200",
      dot: "bg-yellow-500",
      label: "Warning",
    },
    DOWN: {
      bg: "bg-red-50",
      text: "text-red-700",
      border: "border-red-200",
      dot: "bg-red-500",
      label: "Down",
    },
    DISCONNECTED: {
      bg: "bg-gray-50",
      text: "text-gray-700",
      border: "border-gray-200",
      dot: "bg-gray-500",
      label: "Disconnected",
    },
  };

  const config = statusConfig[status] || statusConfig.DISCONNECTED;
  const sizeClasses = size === "large" ? "px-4 py-2 text-base" : "px-3 py-1 text-sm";

  return (
    <span className={`inline-flex items-center gap-2 rounded-lg border font-semibold ${config.bg} ${config.text} ${config.border} ${sizeClasses}`}>
      <span className={`w-2 h-2 rounded-full ${config.dot}`}></span>
      {config.label}
    </span>
  );
}
