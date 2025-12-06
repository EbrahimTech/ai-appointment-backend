"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import copy from "copy-to-clipboard";
import { Plug, MessageSquare, Calendar, RefreshCw, Send, CheckCircle2, XCircle, AlertCircle, Copy } from "lucide-react";

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
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading integrations...</p>
        </div>
      </div>
    );
  }

  if (whatsappQuery.isError || googleQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-4">
          <div className="flex items-center justify-center w-16 h-16 rounded-full bg-red-100 mx-auto">
            <Plug className="w-8 h-8 text-red-600" />
          </div>
          <div>
            <p className="text-base font-medium text-gray-900 mb-1">Unable to load integrations</p>
            <p className="text-sm text-gray-500 mb-4">Please try again</p>
          </div>
          <button
            type="button"
            onClick={() => {
              whatsappQuery.refetch();
              googleQuery.refetch();
            }}
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
          <div className="flex items-start gap-4">
            <div className="flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600 text-white shadow-lg">
              <Plug className="w-7 h-7" />
            </div>
          <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">Integrations</h1>
              <p className="text-sm text-gray-600">Manage WhatsApp and Google Calendar connections</p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* WhatsApp Integration */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-4">
              <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-green-100">
                <MessageSquare className="w-6 h-6 text-green-600" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-gray-900">WhatsApp Integration</h2>
                <p className="text-sm text-gray-600">Send sandbox messages and track delivery</p>
              </div>
            </div>
            <StatusBadge status={whatsapp?.status ?? "DOWN"} />
        </div>

          <div className="grid gap-4 md:grid-cols-3 mb-6">
          <InfoRow label="Provider" value={whatsapp?.provider} />
            <InfoRow label="Last Success" value={whatsapp?.last_success_at} />
            <InfoRow label="Last Error" value={whatsapp?.last_error_at} />
        </div>

          <form className="space-y-4" onSubmit={handleSendTest}>
          <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700" htmlFor="sandbox-phone">
                  Sandbox Phone
              </label>
              <input
                id="sandbox-phone"
                name="sandbox-phone"
                value={toPhone}
                onChange={(event) => setToPhone(event.target.value)}
                placeholder="+15555550123"
                  className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                required
              />
            </div>
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700" htmlFor="template-key">
                  Template Key
              </label>
              <input
                id="template-key"
                name="template-key"
                value={templateKey}
                onChange={(event) => setTemplateKey(event.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              />
            </div>
          </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="variables">
              Variables (JSON)
            </label>
            <textarea
              id="variables"
              name="variables"
              rows={4}
              value={variablesText}
              onChange={(event) => setVariablesText(event.target.value)}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            />
              <p className="text-xs text-gray-500">
              Example: {"{\"name\":\"Omar\",\"slot1\":\"10:00\",\"slot2\":\"14:00\"}"}
            </p>
          </div>
            {testError && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 flex items-start gap-3">
                <XCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-red-900">{testError}</p>
              </div>
            )}
            <div className="flex items-center gap-3">
            <button
              type="submit"
                className="flex items-center gap-2 rounded-lg bg-green-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50 transition-colors shadow-sm"
              disabled={whatsappQuery.isPending}
            >
                <Send className="w-4 h-4" />
                <span>Send Test</span>
            </button>
            <button
              type="button"
              onClick={() => whatsappQuery.refetch()}
                className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
                <RefreshCw className="w-4 h-4" />
                <span>Refresh Status</span>
            </button>
          </div>
        </form>

          {outboxId && (
            <div className="mt-6 rounded-lg border border-gray-200 bg-gray-50 p-5">
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm font-semibold text-gray-900">Outbox #{outboxId}</span>
              <StatusPill state={outboxStatus?.state ?? (isPolling ? "QUEUED" : "QUEUED")} />
              </div>
              <dl className="space-y-2">
                <InfoRow label="Message Type" value={outboxStatus?.message_type ?? "session"} compact />
                <InfoRow label="Provider Message ID" value={outboxStatus?.provider_message_id ?? "—"} compact />
                <InfoRow label="Last Error" value={outboxStatus?.last_error ?? "—"} compact />
                <InfoRow label="Updated At" value={outboxStatus?.updated_at ?? "—"} compact />
              </dl>
              {pollError && (
                <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                  <p className="text-sm text-red-900">{pollError}</p>
                </div>
              )}
            </div>
          )}
          </div>

        {/* Google Calendar Integration */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-4">
              <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-blue-100">
                <Calendar className="w-6 h-6 text-blue-600" />
              </div>
          <div>
                <h2 className="text-xl font-semibold text-gray-900">Google Calendar</h2>
                <p className="text-sm text-gray-600">Keep bookings synced with your Google Calendar</p>
              </div>
          </div>
          <StatusBadge status={google?.status ?? "DISCONNECTED"} />
        </div>
          <div className="grid gap-4 md:grid-cols-2 mb-6">
            <InfoRow label="Last Auth" value={google?.last_auth_at} />
            <InfoRow label="Last Error" value={google?.last_error} />
        </div>
          <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleConnectGoogle}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors shadow-sm"
          >
              <Calendar className="w-4 h-4" />
              <span>Connect Google</span>
          </button>
          <button
            type="button"
            onClick={() => googleQuery.refetch()}
              className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
              <RefreshCw className="w-4 h-4" />
              <span>Refresh Status</span>
          </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    OK: "bg-green-100 text-green-700",
    WARN: "bg-amber-100 text-amber-700",
    DOWN: "bg-red-100 text-red-700",
    DISCONNECTED: "bg-gray-100 text-gray-600",
  };
  const cls = styles[status] ?? styles["DOWN"];
  return (
    <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${cls}`}>
      {status}
    </span>
  );
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
