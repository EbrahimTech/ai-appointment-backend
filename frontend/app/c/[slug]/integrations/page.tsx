"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import copy from "copy-to-clipboard";

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

type OutboxStatus = {
  id: number;
  state: "QUEUED" | "SENT" | "DELIVERED" | "FAILED";
  message_type: string;
  provider_message_id: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
};

export default function ClinicIntegrationsPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;

  const whatsappQuery = useQuery({
    queryKey: ["whatsappStatus", slug],
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
    queryKey: ["googleStatus", slug],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/calendar/google`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load Google status");
      }
      return payload.data as GoogleStatus;
    },
  });

  const whatsapp = useMemo(() => whatsappQuery.data, [whatsappQuery.data]);
  const google = useMemo(() => googleQuery.data, [googleQuery.data]);

  const [toPhone, setToPhone] = useState("");
  const [templateKey, setTemplateKey] = useState("greet");
  const [variablesText, setVariablesText] = useState('{"name":"Test"}');
  const [testError, setTestError] = useState<string | null>(null);
  const [outboxId, setOutboxId] = useState<number | null>(null);
  const [outboxStatus, setOutboxStatus] = useState<OutboxStatus | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [pollError, setPollError] = useState<string | null>(null);

  useEffect(() => {
    if (!outboxId) {
      return;
    }
    let cancelled = false;
    let attempt = 0;
    const startedAt = Date.now();

    async function poll() {
      if (cancelled) return;
      attempt += 1;
      try {
        const response = await fetch(`/api/proxy/clinic/${slug}/outbox/${outboxId}`);
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || "Polling failed");
        }
        const outbox = payload.data.outbox as OutboxStatus;
        setOutboxStatus(outbox);
        if (outbox.state === "DELIVERED" || outbox.state === "FAILED") {
          setIsPolling(false);
          return;
        }
        if (Date.now() - startedAt > 60000) {
          setPollError("Polling timeout after 60 seconds.");
          setIsPolling(false);
          return;
        }
      } catch (error) {
        setPollError(error instanceof Error ? error.message : "Polling failed");
        setIsPolling(false);
        return;
      }
      if (!cancelled) {
        const delay = Math.min(3000, 1500 + attempt * 500);
        setTimeout(poll, delay);
      }
    }

    setIsPolling(true);
    setPollError(null);
    poll();

    return () => {
      cancelled = true;
    };
  }, [outboxId, slug]);

  async function handleSendTest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTestError(null);
    setPollError(null);
    setOutboxStatus(null);
    setOutboxId(null);

    let variables: Record<string, unknown> = {};
    if (variablesText.trim()) {
      try {
        variables = JSON.parse(variablesText);
      } catch {
        setTestError("Variables must be valid JSON.");
        return;
      }
    }

    try {
      const response = await fetch(`/api/proxy/clinic/${slug}/channels/whatsapp/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_sandbox_phone: toPhone,
          template_key: templateKey,
          variables,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        const error = payload.error || "SEND_FAILED";
        if (error === "FORBIDDEN_SANDBOX_NUMBER") {
          setTestError("This phone number is not in the sandbox allowlist.");
        } else if (error === "RATE_LIMIT" || response.status === 429) {
          setTestError("Rate limit exceeded (3 requests per minute). Please wait a moment.");
        } else {
          setTestError(error);
        }
        return;
      }
      setOutboxId(payload.data.outbox_id);
    } catch (error) {
      setTestError(error instanceof Error ? error.message : "SEND_FAILED");
    }
  }

  async function handleConnectGoogle() {
    try {
      const response = await fetch(`/api/proxy/clinic/${slug}/calendar/google/oauth/start`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "OAUTH_START_FAILED");
      }
      const authUrl = payload.data?.auth_url;
      if (authUrl) {
        window.location.href = authUrl;
      }
    } catch (error) {
      alert(error instanceof Error ? error.message : "Unable to start Google OAuth");
    }
  }

  if (whatsappQuery.isPending || googleQuery.isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading integrations...</p>
      </main>
    );
  }

  if (whatsappQuery.isError || googleQuery.isError) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Unable to load integration status.</p>
          <button
            type="button"
            onClick={() => {
              whatsappQuery.refetch();
              googleQuery.refetch();
            }}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="space-y-10 px-6 py-8">
      <section className="rounded-lg border bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold">WhatsApp Integration</h2>
            <p className="text-sm text-muted-foreground">Send sandbox messages and track delivery.</p>
          </div>
          <StatusBadge status={whatsapp?.status ?? "DOWN"} />
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <InfoRow label="Provider" value={whatsapp?.provider} />
          <InfoRow label="Last success" value={whatsapp?.last_success_at} />
          <InfoRow label="Last error" value={whatsapp?.last_error_at} />
        </div>

        <form className="mt-6 space-y-4" onSubmit={handleSendTest}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="sandbox-phone">
                Sandbox phone
              </label>
              <input
                id="sandbox-phone"
                name="sandbox-phone"
                value={toPhone}
                onChange={(event) => setToPhone(event.target.value)}
                placeholder="+15555550123"
                className="w-full rounded border px-3 py-2 text-sm"
                required
              />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="template-key">
                Template key
              </label>
              <input
                id="template-key"
                name="template-key"
                value={templateKey}
                onChange={(event) => setTemplateKey(event.target.value)}
                className="w-full rounded border px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="variables">
              Variables (JSON)
            </label>
            <textarea
              id="variables"
              name="variables"
              rows={4}
              value={variablesText}
              onChange={(event) => setVariablesText(event.target.value)}
              className="w-full rounded border px-3 py-2 text-sm font-mono"
            />
            <p className="text-xs text-muted-foreground">
              Example: {"{\"name\":\"Omar\",\"slot1\":\"10:00\",\"slot2\":\"14:00\"}"}
            </p>
          </div>
          {testError ? <p className="text-sm text-red-600">{testError}</p> : null}
          <div className="flex items-center gap-2">
            <button
              type="submit"
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              disabled={whatsappQuery.isPending}
            >
              Send test
            </button>
            <button
              type="button"
              onClick={() => whatsappQuery.refetch()}
              className="rounded-md border px-3 py-2 text-sm"
            >
              Refresh status
            </button>
          </div>
        </form>

        {outboxId ? (
          <div className="mt-6 rounded-md border bg-slate-50 p-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">Outbox #{outboxId}</span>
              <StatusPill state={outboxStatus?.state ?? (isPolling ? "QUEUED" : "QUEUED")} />
            </div>
            <dl className="mt-2 space-y-1">
              <InfoRow label="Message type" value={outboxStatus?.message_type ?? "session"} compact />
              <InfoRow label="Provider message id" value={outboxStatus?.provider_message_id ?? "—"} compact />
              <InfoRow label="Last error" value={outboxStatus?.last_error ?? "—"} compact />
              <InfoRow label="Updated at" value={outboxStatus?.updated_at ?? "—"} compact />
            </dl>
            {pollError ? <p className="mt-2 text-sm text-red-600">{pollError}</p> : null}
          </div>
        ) : null}
      </section>

      <section className="rounded-lg border bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold">Google Calendar</h2>
            <p className="text-sm text-muted-foreground">Keep bookings synced with your Google Calendar.</p>
          </div>
          <StatusBadge status={google?.status ?? "DISCONNECTED"} />
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <InfoRow label="Last auth" value={google?.last_auth_at} />
          <InfoRow label="Last error" value={google?.last_error} />
        </div>
        <div className="mt-6 flex items-center gap-3">
          <button
            type="button"
            onClick={handleConnectGoogle}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Connect Google
          </button>
          <button
            type="button"
            onClick={() => googleQuery.refetch()}
            className="rounded-md border px-3 py-2 text-sm"
          >
            Refresh status
          </button>
        </div>
      </section>
    </main>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    OK: "bg-emerald-100 text-emerald-700",
    WARN: "bg-amber-100 text-amber-700",
    DOWN: "bg-red-100 text-red-700",
    DISCONNECTED: "bg-gray-100 text-gray-600",
  };
  const cls = styles[status] ?? styles["DOWN"];
  return <span className={`rounded-full px-3 py-1 text-xs font-semibold ${cls}`}>{status}</span>;
}

function InfoRow({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: string | number | null | undefined;
  compact?: boolean;
}) {
  const display = value === null || value === undefined || value === "" ? "—" : value;
  if (compact) {
    return (
      <div className="flex items-center gap-2 text-xs text-slate-600">
        <span className="font-semibold text-slate-700">{label}:</span>
        <span>{display}</span>
      </div>
    );
  }
  return (
    <div className="flex flex-col text-sm">
      <span className="font-semibold text-slate-700">{label}</span>
      <span>{display}</span>
    </div>
  );
}

function StatusPill({ state }: { state: string }) {
  const colors: Record<string, string> = {
    QUEUED: "bg-amber-100 text-amber-700",
    SENT: "bg-blue-100 text-blue-700",
    DELIVERED: "bg-emerald-100 text-emerald-700",
    FAILED: "bg-red-100 text-red-700",
  };
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${colors[state] ?? colors.QUEUED}`}>{state}</span>;
}
