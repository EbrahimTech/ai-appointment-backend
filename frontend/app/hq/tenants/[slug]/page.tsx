
"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";

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
      return payload.data.items as TenantItem[];
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

  if (tenantsQuery.isPending || tenantsQuery.isError) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading tenant details...</p>
      </main>
    );
  }

  const tenant = tenantsQuery.data.find((item) => item.clinic.slug === slug);
  if (!tenant) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4 text-center">
        <p className="text-sm text-red-600">Tenant not found.</p>
      </main>
    );
  }

  const isImpersonating = support?.clinicSlug === slug;

  return (
    <main className="space-y-8 px-6 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{tenant.clinic.name}</h1>
          <p className="text-sm text-muted-foreground">Slug: {tenant.clinic.slug} � ID: {tenant.clinic.id}</p>
          <p className="text-sm text-muted-foreground">TTFR p95 (ms): {tenant.last_ttfr_p95_ms}</p>
        </div>
        <div className="flex items-center gap-3">
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={2}
            className="w-64 rounded border px-3 py-2 text-sm"
          />
          {isImpersonating ? (
            <button
              type="button"
              onClick={() => stopSupport.mutate()}
              className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              disabled={stopSupport.isPending}
            >
              {stopSupport.isPending ? "Stopping..." : "Stop impersonation"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => startSupport.mutate({ clinic_id: tenant.clinic.id })}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              disabled={startSupport.isPending}
            >
              {startSupport.isPending ? "Starting..." : "Start impersonation"}
            </button>
          )}
        </div>
      </header>

      {feedback ? <Alert variant="success" message={feedback} /> : null}
      {error ? <Alert variant="error" message={error} /> : null}

      <section className="space-y-4 rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Channels</h2>
        {whatsappQuery.isPending ? (
          <p className="text-sm text-muted-foreground">Loading WhatsApp status...</p>
        ) : whatsappQuery.isError ? (
          <p className="text-sm text-red-600">Unable to load WhatsApp status.</p>
        ) : (
          <StatusCard
            title="WhatsApp"
            status={whatsappQuery.data?.status ?? "DOWN"}
            details={[
              { label: "Provider", value: whatsappQuery.data?.provider ?? "�" },
              { label: "Last success", value: whatsappQuery.data?.last_success_at ?? "�" },
              { label: "Last error", value: whatsappQuery.data?.last_error_at ?? "�" },
            ]}
          />
        )}
      </section>

      <section className="space-y-4 rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Google Calendar</h2>
        {googleQuery.isPending ? (
          <p className="text-sm text-muted-foreground">Loading Google status...</p>
        ) : googleQuery.isError ? (
          <p className="text-sm text-red-600">Unable to load Google status.</p>
        ) : (
          <StatusCard
            title="Google Calendar"
            status={googleQuery.data?.status ?? "DISCONNECTED"}
            details={[
              { label: "Last auth", value: googleQuery.data?.last_auth_at ?? "�" },
              { label: "Last error", value: googleQuery.data?.last_error ?? "�" },
            ]}
          />
        )}
      </section>
    </main>
  );
}

function Alert({ variant, message }: { variant: "success" | "error"; message: string }) {
  const styles =
    variant === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : "border-red-200 bg-red-50 text-red-700";
  return <div className={`rounded border px-4 py-3 text-sm ${styles}`}>{message}</div>;
}

function StatusCard({
  title,
  status,
  details,
}: {
  title: string;
  status: string;
  details: { label: string; value: string }[];
}) {
  return (
    <div className="rounded border bg-white shadow-sm">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div>
          <p className="text-sm font-medium text-muted-foreground">{title}</p>
          <p className="text-lg font-semibold">{status}</p>
        </div>
      </div>
      <dl className="grid gap-3 px-4 py-3 text-sm">
        {details.map((detail) => (
          <div key={detail.label} className="flex justify-between gap-4">
            <dt className="text-muted-foreground">{detail.label}</dt>
            <dd className="text-right">{detail.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

