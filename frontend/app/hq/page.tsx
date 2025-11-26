"use client";

import Link from "next/link";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import copy from "copy-to-clipboard";
import { z } from "zod";

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

  const tenants = useMemo(() => tenantsQuery.data?.data?.items ?? [], [tenantsQuery.data]);

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
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-gray-500">Loading tenants...</p>
      </div>
    );
  }

  if (tenantsQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-red-600">Unable to load tenants.</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Tenants</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage clinics, invite owners, and monitor operational health
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/hq/metrics"
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Global Metrics
          </Link>
          <button
            type="button"
            onClick={() => {
              setShowModal(true);
              setInviteToken(null);
              setSuccessMessage(null);
            }}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            + New Tenant
          </button>
        </div>
      </div>

      {successMessage ? (
        <div className="rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          <div className="flex items-center justify-between">
            <span>{successMessage}</span>
            {inviteToken ? (
              <div className="flex items-center gap-2">
                <code className="rounded bg-white px-3 py-1.5 text-xs font-mono text-gray-800 border border-green-200">
                  {inviteToken}
                </code>
                <button
                  type="button"
                  onClick={handleCopyToken}
                  className="text-xs font-medium text-green-700 hover:text-green-800 underline"
                >
                  Copy Link
                </button>
              </div>
            ) : null}
          </div>
          {inviteToken && (
            <p className="mt-2 text-xs text-green-600">
              Send this link to the clinic owner:{" "}
              <span className="font-mono">
                {typeof window !== "undefined" && `${window.location.origin}/accept-invite?token=${inviteToken}`}
              </span>
            </p>
          )}
        </div>
      ) : null}

      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700">
                Clinic
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700">
                Channels
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700">
                Calendar
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700">
                Performance
              </th>
              <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-700">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {tenants.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-sm text-gray-500">
                  No tenants found. Create your first tenant to get started.
                </td>
              </tr>
            ) : (
              tenants.map((item: any) => (
                <tr key={item.clinic.slug} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div>
                      <div className="text-sm font-semibold text-gray-900">{item.clinic.name}</div>
                      <div className="text-xs text-gray-500">{item.clinic.slug}</div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={item.channels_status} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={item.calendar_status} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-gray-900">
                      {item.last_ttfr_p95_ms ? `${item.last_ttfr_p95_ms}ms` : "—"}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                    <Link
                      href={`/hq/tenants/${item.clinic.slug}`}
                      className="text-blue-600 hover:text-blue-800 font-medium"
                    >
                      View Details
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-2xl rounded-lg bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-xl font-semibold text-gray-900">Create New Tenant</h2>
                <p className="text-sm text-gray-500 mt-1">Add a new clinic to the system</p>
              </div>
              <button
                type="button"
                className="text-gray-400 hover:text-gray-600 p-1"
                onClick={() => setShowModal(false)}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <form className="mt-4 space-y-4" onSubmit={handleSubmit}>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-sm font-medium" htmlFor="name">
                    Name
                  </label>
                  <input
                    id="name"
                    name="name"
                    value={formState.name}
                    onChange={handleChange}
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium" htmlFor="slug">
                    Slug
                  </label>
                  <input
                    id="slug"
                    name="slug"
                    value={formState.slug}
                    onChange={handleChange}
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-sm font-medium" htmlFor="default_lang">
                    Default language
                  </label>
                  <select
                    id="default_lang"
                    name="default_lang"
                    value={formState.default_lang}
                    onChange={handleChange}
                    className="w-full rounded border px-3 py-2 text-sm"
                  >
                    <option value="en">English</option>
                    <option value="ar">Arabic</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium" htmlFor="tz">
                    Timezone
                  </label>
                  <input
                    id="tz"
                    name="tz"
                    value={formState.tz}
                    onChange={handleChange}
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                    placeholder="UTC"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-sm font-medium" htmlFor="owner_email">
                    Owner email
                  </label>
                  <input
                    id="owner_email"
                    name="owner_email"
                    type="email"
                    value={formState.owner_email}
                    onChange={handleChange}
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium" htmlFor="owner_name">
                    Owner name
                  </label>
                  <input
                    id="owner_name"
                    name="owner_name"
                    value={formState.owner_name}
                    onChange={handleChange}
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                  />
                </div>
              </div>
              {formErrors ? (
                <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {formErrors}
                </div>
              ) : null}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-200">
                <button
                  type="button"
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                  onClick={() => setShowModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
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
  );
}

function StatusBadge({ status }: { status: string }) {
  const statusColors: Record<string, string> = {
    OK: "bg-green-100 text-green-800",
    WARN: "bg-yellow-100 text-yellow-800",
    DOWN: "bg-red-100 text-red-800",
    DISCONNECTED: "bg-gray-100 text-gray-800",
  };
  const color = statusColors[status] || "bg-gray-100 text-gray-800";
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}>
      {status}
    </span>
  );
}
