"use client";

import Link from "next/link";

import { useMemo, useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import copy from "copy-to-clipboard";
import { z } from "zod";
import { X, Building2, BarChart3, Plus, Copy, CheckCircle2, ExternalLink, Activity, MessageSquare, Calendar } from "lucide-react";

const tenantSchema = z.object({
  name: z.string().min(2),
  slug: z.string().min(2).regex(/^[a-z0-9-]+$/),
  default_lang: z.enum(["en", "ar"]),
  tz: z.string().min(2),
  owner_email: z.string().email(),
  owner_name: z.string().min(2),
});

type TenantInput = z.infer<typeof tenantSchema>;

export default function HQTenantsPage() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [formState, setFormState] = useState<TenantInput>({
    name: "",
    slug: "",
    default_lang: "en",
    tz: "UTC",
    owner_email: "",
    owner_name: "",
  });
  const [formErrors, setFormErrors] = useState<string | null>(null);
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [inviteLink, setInviteLink] = useState<string>("");

  const tenantsQuery = useQuery({
    queryKey: ["hqTenants"],
    queryFn: async () => {
      const response = await fetch("/api/proxy/hq/tenants");
      if (!response.ok) {
        throw new Error("LOAD_FAILED");
      }
      return response.json();
    },
  });

  const createTenant = useMutation({
    mutationFn: async (input: TenantInput) => {
      const response = await fetch("/api/proxy/hq/tenants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "CREATE_FAILED");
      }
      return payload.data;
    },
    onSuccess: (data) => {
      setInviteToken(data.invite_token);
      setSuccessMessage(`Tenant ${data.clinic.name} created successfully.`);
      setShowModal(false);
      setFormState({
        name: "",
        slug: "",
        default_lang: "en",
        tz: "UTC",
        owner_email: "",
        owner_name: "",
      });
      setFormErrors(null);
      queryClient.invalidateQueries({ queryKey: ["hqTenants"] });
    },
    onError: (error: Error) => {
      setFormErrors(error.message);
    },
  });

  const tenants = useMemo(() => {
    const items = tenantsQuery.data?.data?.items;
    return Array.isArray(items) ? items : [];
  }, [tenantsQuery.data]);

  // Generate invite link only on client side to prevent hydration mismatch
  useEffect(() => {
    if (inviteToken && typeof window !== "undefined") {
      setInviteLink(`${window.location.origin}/accept-invite?token=${inviteToken}`);
    } else {
      setInviteLink("");
    }
  }, [inviteToken]);

  function handleChange(event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    const { name, value } = event.target;
    setFormState((prev) => ({ ...prev, [name]: value }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = tenantSchema.safeParse(formState);
    if (!parsed.success) {
      setFormErrors(parsed.error.issues[0]?.message ?? "Invalid form");
      return;
    }
    createTenant.mutate(parsed.data);
  }

  function handleCopyToken() {
    if (inviteToken) {
      copy(inviteToken);
      setSuccessMessage("Invite token copied to clipboard.");
    }
  }

  if (tenantsQuery.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading tenants...</p>
        </div>
      </div>
    );
  }

  if (tenantsQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Unable to load tenants.</p>
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

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Header Section */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-lg">
                  <Building2 className="w-6 h-6" />
                </div>
                <div>
                  <h1 className="text-3xl font-bold text-gray-900">Tenants</h1>
                  <p className="text-sm text-gray-600 mt-1">
                    Manage clinics, invite owners, and monitor operational health
                  </p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Link
                href="/hq/metrics"
                className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors shadow-sm"
              >
                <BarChart3 className="w-4 h-4" />
                Global Metrics
              </Link>
              <button
                type="button"
                onClick={() => {
                  setShowModal(true);
                  setInviteToken(null);
                  setSuccessMessage(null);
                }}
                className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors shadow-sm"
              >
                <Plus className="w-4 h-4" />
                New Tenant
              </button>
            </div>
          </div>
        </div>

        {/* Success Message */}
        {successMessage ? (
          <div className="mb-6 rounded-xl border border-green-200 bg-gradient-to-r from-green-50 to-emerald-50 px-6 py-4 shadow-sm">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 text-green-600 mt-0.5 flex-shrink-0" />
              <div className="flex-1">
                <p className="text-sm font-medium text-green-900 mb-2">{successMessage}</p>
                {inviteToken && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 flex-wrap">
                      <code className="rounded-lg bg-white px-4 py-2 text-xs font-mono text-gray-800 border border-green-200 shadow-sm">
                        {inviteToken}
                      </code>
                      <button
                        type="button"
                        onClick={handleCopyToken}
                        className="flex items-center gap-1.5 rounded-lg bg-green-600 px-3 py-2 text-xs font-medium text-white hover:bg-green-700 transition-colors"
                      >
                        <Copy className="w-3.5 h-3.5" />
                        Copy Token
                      </button>
                    </div>
                    <div className="rounded-lg bg-white border border-green-200 p-3">
                      <p className="text-xs font-medium text-green-800 mb-1">Invitation Link:</p>
                      <div className="flex items-center gap-2">
                        <code className="flex-1 text-xs font-mono text-gray-700 break-all">
                          {inviteLink || "Loading..."}
                        </code>
                        <button
                          type="button"
                          onClick={() => {
                            if (inviteLink) {
                              copy(inviteLink);
                              setSuccessMessage("Invitation link copied to clipboard!");
                            }
                          }}
                          className="flex-shrink-0 p-1.5 rounded hover:bg-green-50 transition-colors"
                          title="Copy link"
                          disabled={!inviteLink}
                        >
                          <Copy className="w-4 h-4 text-green-600" />
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : null}

        {/* Tenants Table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
                <tr>
                  <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-gray-700">
                    Clinic
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-gray-700">
                    <div className="flex items-center gap-2">
                      <MessageSquare className="w-4 h-4" />
                      Channels
                    </div>
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-gray-700">
                    <div className="flex items-center gap-2">
                      <Calendar className="w-4 h-4" />
                      Calendar
                    </div>
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wider text-gray-700">
                    <div className="flex items-center gap-2">
                      <Activity className="w-4 h-4" />
                      Performance
                    </div>
                  </th>
                  <th className="px-6 py-4 text-right text-xs font-semibold uppercase tracking-wider text-gray-700">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {tenants.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center">
                      <div className="flex flex-col items-center gap-3">
                        <Building2 className="w-12 h-12 text-gray-400" />
                        <div>
                          <p className="text-sm font-medium text-gray-900">No tenants found</p>
                          <p className="text-xs text-gray-500 mt-1">Create your first tenant to get started</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setShowModal(true);
                            setInviteToken(null);
                            setSuccessMessage(null);
                          }}
                          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
                        >
                          <Plus className="w-4 h-4" />
                          Create Tenant
                        </button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  tenants.map((item: any) => {
                    const slug = item?.clinic?.slug;
                    if (!slug) return null;
                    return (
                      <tr key={slug} className="hover:bg-blue-50/30 transition-colors group">
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-sm group-hover:shadow-md transition-shadow">
                              <Building2 className="w-5 h-5" />
                            </div>
                            <div>
                              <div className="text-sm font-semibold text-gray-900">{item.clinic?.name || "—"}</div>
                              <div className="text-xs text-gray-500 font-mono">{slug}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <StatusBadge status={item.channels_status || "DISCONNECTED"} />
                        </td>
                        <td className="px-6 py-4">
                          <StatusBadge status={item.calendar_status || "DISCONNECTED"} />
                        </td>
                        <td className="px-6 py-4">
                          {item.last_ttfr_p95_ms ? (
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-gray-900">{item.last_ttfr_p95_ms}ms</span>
                              <span className="text-xs text-gray-500">p95</span>
                            </div>
                          ) : (
                            <span className="text-sm text-gray-400">—</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <Link
                            href={`/hq/tenants/${slug}`}
                            className="inline-flex items-center gap-1.5 text-blue-600 hover:text-blue-700 font-medium text-sm transition-colors"
                          >
                            View Details
                            <ExternalLink className="w-3.5 h-3.5" />
                          </Link>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Create Tenant Modal */}
        {showModal ? (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
            <div className="w-full max-w-2xl rounded-xl bg-white shadow-2xl transform transition-all">
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-gray-200 px-6 py-5 rounded-t-xl">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-blue-600 text-white">
                      <Plus className="w-5 h-5" />
                    </div>
                    <div>
                      <h2 className="text-xl font-semibold text-gray-900">Create New Tenant</h2>
                      <p className="text-sm text-gray-600 mt-0.5">Add a new clinic to the system</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="text-gray-400 hover:text-gray-600 p-1.5 rounded-lg hover:bg-white/50 transition-colors"
                    onClick={() => setShowModal(false)}
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>
              <form className="p-6 space-y-5" onSubmit={handleSubmit}>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700" htmlFor="name">
                      Clinic Name
                    </label>
                    <input
                      id="name"
                      name="name"
                      value={formState.name}
                      onChange={handleChange}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      placeholder="e.g., Demo Dental"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700" htmlFor="slug">
                      Slug
                    </label>
                    <input
                      id="slug"
                      name="slug"
                      value={formState.slug}
                      onChange={handleChange}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      placeholder="e.g., demo-dental"
                      required
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700" htmlFor="default_lang">
                      Default Language
                    </label>
                    <select
                      id="default_lang"
                      name="default_lang"
                      value={formState.default_lang}
                      onChange={handleChange}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    >
                      <option value="en">English</option>
                      <option value="ar">Arabic</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700" htmlFor="tz">
                      Timezone
                    </label>
                    <input
                      id="tz"
                      name="tz"
                      value={formState.tz}
                      onChange={handleChange}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      placeholder="UTC"
                      required
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700" htmlFor="owner_email">
                      Owner Email
                    </label>
                    <input
                      id="owner_email"
                      name="owner_email"
                      type="email"
                      value={formState.owner_email}
                      onChange={handleChange}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      placeholder="owner@example.com"
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700" htmlFor="owner_name">
                      Owner Name
                    </label>
                    <input
                      id="owner_name"
                      name="owner_name"
                      value={formState.owner_name}
                      onChange={handleChange}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      placeholder="John Doe"
                      required
                    />
                  </div>
                </div>
                {formErrors ? (
                  <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                    {formErrors}
                  </div>
                ) : null}
                <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200">
                  <button
                    type="button"
                    className="rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                    onClick={() => setShowModal(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
                    disabled={createTenant.isPending}
                  >
                    {createTenant.isPending ? "Creating..." : "Create Tenant"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const statusConfig: Record<string, { bg: string; text: string; dot: string; label: string }> = {
    OK: {
      bg: "bg-green-50",
      text: "text-green-700",
      dot: "bg-green-500",
      label: "OK",
    },
    WARN: {
      bg: "bg-yellow-50",
      text: "text-yellow-700",
      dot: "bg-yellow-500",
      label: "WARN",
    },
    DOWN: {
      bg: "bg-red-50",
      text: "text-red-700",
      dot: "bg-red-500",
      label: "DOWN",
    },
    DISCONNECTED: {
      bg: "bg-gray-50",
      text: "text-gray-700",
      dot: "bg-gray-500",
      label: "DISCONNECTED",
    },
  };

  const config = statusConfig[status] || statusConfig.DISCONNECTED;

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-semibold ${config.bg} ${config.text} ${config.bg.replace("bg-", "border-").replace("-50", "-200")}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${config.dot}`}></span>
      {config.label}
    </span>
  );
}
