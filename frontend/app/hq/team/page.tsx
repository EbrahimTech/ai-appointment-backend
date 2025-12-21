"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import {
  Users,
  UserPlus,
  RefreshCw,
  Mail,
  Shield,
  Edit,
  Trash2,
  X,
  CheckCircle2,
  XCircle,
  AlertCircle,
  KeyRound,
} from "lucide-react";

type StaffMember = {
  id: number;
  email: string;
  name: string;
  role: "SUPERADMIN" | "OPS";
  is_active: boolean;
  last_login: string | null;
  created_at: string;
};

const createSchema = z.object({
  email: z.string().email(),
  role: z.enum(["SUPERADMIN", "OPS"]),
  first_name: z.string().optional(),
  last_name: z.string().optional(),
  password: z.string().optional(),
});

const updateSchema = z.object({
  role: z.enum(["SUPERADMIN", "OPS"]),
});

const ROLE_LABELS: Record<StaffMember["role"], string> = {
  SUPERADMIN: "Super Admin",
  OPS: "Ops",
};

export default function HQTeamPage() {
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tempPassword, setTempPassword] = useState<string | null>(null);

  const staffQuery = useQuery({
    queryKey: ["hq-staff"],
    queryFn: async () => {
      const response = await fetch("/api/proxy/hq/staff");
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load staff");
      }
      return payload.data.items as StaffMember[];
    },
  });

  const meQuery = useQuery({
    queryKey: ["session-me"],
    queryFn: async () => {
      const response = await fetch("/api/session/me");
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load session");
      }
      return payload;
    },
  });

  const hqRole = meQuery.data?.data?.hq_role ?? null;
  const readOnly = hqRole !== "SUPERADMIN";

  const createMutation = useMutation({
    mutationFn: async (payload: z.infer<typeof createSchema>) => {
      const response = await fetch("/api/proxy/hq/staff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "CREATE_FAILED");
      }
      return result.data as { temp_password?: string | null; email: string };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["hq-staff"] });
      setFeedback(`Staff member added: ${data.email}.`);
      setError(null);
      setTempPassword(data.temp_password || null);
    },
    onError: (err: Error) => {
      setError(humanizeError(err.message));
      setFeedback(null);
      setTempPassword(null);
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, role }: { id: number; role: z.infer<typeof updateSchema>["role"] }) => {
      const response = await fetch(`/api/proxy/hq/staff/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "UPDATE_FAILED");
      }
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["hq-staff"] });
      setFeedback("Role updated successfully.");
      setError(null);
      setSelectedId(null);
    },
    onError: (err: Error) => {
      setError(humanizeError(err.message));
      setFeedback(null);
    },
  });

  const removeMutation = useMutation({
    mutationFn: async (id: number) => {
      const response = await fetch(`/api/proxy/hq/staff/${id}`, {
        method: "DELETE",
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "REMOVE_FAILED");
      }
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["hq-staff"] });
      setFeedback("Staff member removed.");
      setError(null);
    },
    onError: (err: Error) => {
      setError(humanizeError(err.message));
      setFeedback(null);
    },
  });

  const staffMembers = useMemo(() => staffQuery.data ?? [], [staffQuery.data]);

  function handleInvite(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTempPassword(null);
    if (readOnly) {
      setError("Only Super Admin can manage HQ staff.");
      setFeedback(null);
      return;
    }
    const formData = new FormData(event.currentTarget);
    const payload = {
      email: String(formData.get("email") || ""),
      role: String(formData.get("role") || "OPS").toUpperCase(),
      first_name: String(formData.get("first_name") || ""),
      last_name: String(formData.get("last_name") || ""),
      password: String(formData.get("password") || ""),
    };
    const parsed = createSchema.safeParse(payload);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid staff data");
      setFeedback(null);
      return;
    }
    createMutation.mutate(parsed.data);
    event.currentTarget.reset();
  }

  if (staffQuery.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading HQ staff...</p>
        </div>
      </div>
    );
  }

  if (staffQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-4">
          <div className="flex items-center justify-center w-16 h-16 rounded-full bg-red-100 mx-auto">
            <Users className="w-8 h-8 text-red-600" />
          </div>
          <div>
            <p className="text-base font-medium text-gray-900 mb-1">Unable to load staff</p>
            <p className="text-sm text-gray-500 mb-4">Please try again</p>
          </div>
          <button
            type="button"
            onClick={() => staffQuery.refetch()}
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
              <div className="flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br from-indigo-500 to-blue-600 text-white shadow-lg">
                <Users className="w-7 h-7" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900 mb-2">HQ Team</h1>
                <p className="text-sm text-gray-600">Manage HQ staff access and roles</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => staffQuery.refetch()}
              disabled={staffQuery.isFetching}
              className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors shadow-sm"
            >
              <RefreshCw className={`w-4 h-4 ${staffQuery.isFetching ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Alerts */}
        {readOnly && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-900">Read-only mode</p>
              <p className="text-xs text-amber-700 mt-0.5">
                Only Super Admin accounts can add or update HQ staff.
              </p>
            </div>
          </div>
        )}

        {feedback && (
          <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-green-900">{feedback}</p>
              {tempPassword ? (
                <p className="mt-2 text-xs text-green-800">
                  Temporary password: <span className="font-mono">{tempPassword}</span>
                </p>
              ) : null}
            </div>
            <button type="button" onClick={() => setFeedback(null)} className="text-green-600 hover:text-green-800">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 flex items-start gap-3">
            <XCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-red-900">{error}</p>
            </div>
            <button type="button" onClick={() => setError(null)} className="text-red-600 hover:text-red-800">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Add Staff Section */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-blue-100">
              <UserPlus className="w-5 h-5 text-blue-600" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900">Add Staff</h2>
          </div>
          <form className="grid grid-cols-1 gap-4 md:grid-cols-2" onSubmit={handleInvite}>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="staff-email">
                <Mail className="w-4 h-4 inline mr-1" />
                Email Address
              </label>
              <input
                id="staff-email"
                name="email"
                type="email"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                placeholder="hq.staff@example.com"
                required
              />
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="staff-role">
                <Shield className="w-4 h-4 inline mr-1" />
                Role
              </label>
              <select
                id="staff-role"
                name="role"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              >
                <option value="SUPERADMIN">Super Admin</option>
                <option value="OPS">Ops</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="staff-first-name">
                First Name
              </label>
              <input
                id="staff-first-name"
                name="first_name"
                type="text"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                placeholder="First name"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="staff-last-name">
                Last Name
              </label>
              <input
                id="staff-last-name"
                name="last_name"
                type="text"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                placeholder="Last name"
              />
            </div>

            <div className="space-y-2 md:col-span-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="staff-password">
                <KeyRound className="w-4 h-4 inline mr-1" />
                Password (optional)
              </label>
              <input
                id="staff-password"
                name="password"
                type="text"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                placeholder="Leave empty to auto-generate"
              />
            </div>

            <div className="md:col-span-2">
              <button
                type="submit"
                className="flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
                disabled={createMutation.isPending || readOnly}
              >
                <UserPlus className="w-4 h-4" />
                <span>{createMutation.isPending ? "Adding..." : "Add Staff"}</span>
              </button>
            </div>
          </form>
        </div>

        {/* Staff Table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
                <tr>
                  <Header label="Name" />
                  <Header label="Email" />
                  <Header label="Role" />
                  <Header label="Status" />
                  <Header label="Last Login" />
                  <Header label="Actions" align="right" />
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {staffMembers.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center">
                      <div className="flex flex-col items-center">
                        <Users className="w-12 h-12 text-gray-400 mb-3" />
                        <p className="text-sm font-medium text-gray-900 mb-1">No staff yet</p>
                        <p className="text-xs text-gray-500">Add the first HQ staff member to get started</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  staffMembers.map((member) => (
                    <tr key={member.id} className="hover:bg-gray-50 transition-colors">
                      <Cell>
                        <div className="text-sm font-medium text-gray-900">{member.name || "Unknown"}</div>
                      </Cell>
                      <Cell>
                        <div className="text-sm text-gray-600">{member.email}</div>
                      </Cell>
                      <Cell>
                        {selectedId === member.id ? (
                          <select
                            defaultValue={member.role}
                            onChange={(event) =>
                              updateMutation.mutate({
                                id: member.id,
                                role: event.target.value as StaffMember["role"],
                              })
                            }
                            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                          >
                            <option value="SUPERADMIN">Super Admin</option>
                            <option value="OPS">Ops</option>
                          </select>
                        ) : (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                            {ROLE_LABELS[member.role]}
                          </span>
                        )}
                      </Cell>
                      <Cell>
                        <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            member.is_active ? "bg-emerald-100 text-emerald-700" : "bg-gray-100 text-gray-700"
                          }`}
                        >
                          {member.is_active ? "Active" : "Inactive"}
                        </span>
                      </Cell>
                      <Cell>
                        <div className="text-xs text-gray-500">
                          {member.last_login ? new Date(member.last_login).toLocaleString() : "Never"}
                        </div>
                      </Cell>
                      <Cell align="right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-blue-600 hover:bg-blue-50 disabled:opacity-50 transition-colors"
                            onClick={() => setSelectedId(selectedId === member.id ? null : member.id)}
                            disabled={readOnly}
                          >
                            <Edit className="w-3.5 h-3.5" />
                            <span>{selectedId === member.id ? "Close" : "Change Role"}</span>
                          </button>
                          <button
                            type="button"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors"
                            onClick={() => {
                              if (readOnly) {
                                setError("Only Super Admin can remove staff.");
                                return;
                              }
                              removeMutation.mutate(member.id);
                            }}
                            disabled={removeMutation.isPending || readOnly}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span>Remove</span>
                          </button>
                        </div>
                      </Cell>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function Header({ label, align = "left" }: { label: string; align?: "left" | "right" }) {
  return (
    <th className={`px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider ${align === "right" ? "text-right" : "text-left"}`}>
      {label}
    </th>
  );
}

function Cell({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return <td className={`px-6 py-4 whitespace-nowrap text-sm ${align === "right" ? "text-right" : ""}`}>{children}</td>;
}

function humanizeError(code: string | undefined) {
  if (!code) return "Something went wrong.";
  const map: Record<string, string> = {
    INVALID_ROLE: "Invalid role selected.",
    INVALID_EMAIL: "Please provide a valid email address.",
    INVALID_PAYLOAD: "Please fill in the required fields.",
    ALREADY_STAFF: "This user already has an HQ staff role.",
    CANNOT_REMOVE_SELF: "You cannot remove your own account.",
    CANNOT_DEMOTE_SELF: "You cannot change your own role to a lower access level.",
  };
  return map[code] ?? code.replace(/_/g, " ");
}
