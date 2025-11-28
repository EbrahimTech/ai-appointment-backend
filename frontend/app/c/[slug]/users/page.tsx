"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { z } from "zod";
import { Users, UserPlus, RefreshCw, Mail, Shield, Edit, Trash2, X, CheckCircle2, XCircle, AlertCircle } from "lucide-react";

type Membership = {
  id: number;
  email: string;
  name: string;
  role: "OWNER" | "ADMIN" | "STAFF" | "VIEWER";
};

const inviteSchema = z.object({
  email: z.string().email(),
  role: z.enum(["OWNER", "ADMIN", "STAFF", "VIEWER"]),
});

const updateSchema = z.object({
  role: z.enum(["OWNER", "ADMIN", "STAFF", "VIEWER"]),
});

export default function UsersPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const queryClient = useQueryClient();
  const { support } = useSupportSession();
  const readOnly = Boolean(support);

  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const usersQuery = useQuery({
    queryKey: ["clinic-users", slug],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/users`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load users");
      }
      return payload.data.items as Membership[];
    },
  });

  const inviteMutation = useMutation({
    mutationFn: async (payload: z.infer<typeof inviteSchema>) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "INVITE_FAILED");
      }
      return result.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["clinic-users", slug] });
      setFeedback(`Invitation sent to ${data.email}.`);
      setError(null);
    },
    onError: (err: Error) => {
      setError(humanizeError(err.message));
      setFeedback(null);
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, role }: { id: number; role: z.infer<typeof updateSchema>["role"] }) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/users/${id}`, {
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
      queryClient.invalidateQueries({ queryKey: ["clinic-users", slug] });
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
      const response = await fetch(`/api/proxy/clinic/${slug}/users/${id}`, {
        method: "DELETE",
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "REMOVE_FAILED");
      }
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clinic-users", slug] });
      setFeedback("Member removed.");
      setError(null);
    },
    onError: (err: Error) => {
      setError(humanizeError(err.message));
      setFeedback(null);
    },
  });

  const users = useMemo(() => usersQuery.data ?? [], [usersQuery.data]);

  useEffect(() => {
    if (readOnly) {
      setSelectedId(null);
    }
  }, [readOnly]);

  function handleInvite(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly) {
      setError("Cannot invite members while impersonating. End support session first.");
      setFeedback(null);
      return;
    }
    const formData = new FormData(event.currentTarget);
    const payload = {
      email: String(formData.get("email") || ""),
      role: String(formData.get("role") || "STAFF").toUpperCase(),
    };
    const parsed = inviteSchema.safeParse(payload);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid invite data");
      setFeedback(null);
      return;
    }
    inviteMutation.mutate(parsed.data);
    event.currentTarget.reset();
  }

  if (usersQuery.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading users...</p>
        </div>
      </div>
    );
  }

  if (usersQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-4">
          <div className="flex items-center justify-center w-16 h-16 rounded-full bg-red-100 mx-auto">
            <Users className="w-8 h-8 text-red-600" />
          </div>
          <div>
            <p className="text-base font-medium text-gray-900 mb-1">Unable to load users</p>
            <p className="text-sm text-gray-500 mb-4">Please try again</p>
          </div>
          <button
            type="button"
            onClick={() => usersQuery.refetch()}
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
              <div className="flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-600 text-white shadow-lg">
                <Users className="w-7 h-7" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900 mb-2">Clinic Members</h1>
                <p className="text-sm text-gray-600">Invite staff and manage access roles</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => usersQuery.refetch()}
              disabled={usersQuery.isFetching}
              className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors shadow-sm"
            >
              <RefreshCw className={`w-4 h-4 ${usersQuery.isFetching ? "animate-spin" : ""}`} />
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
                You are impersonating a clinic. Member management is disabled until the support session ends.
              </p>
            </div>
          </div>
        )}

        {feedback && (
          <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-green-900">{feedback}</p>
            </div>
            <button
              type="button"
              onClick={() => setFeedback(null)}
              className="text-green-600 hover:text-green-800"
            >
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
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-red-600 hover:text-red-800"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Invite Member Section */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-blue-100">
              <UserPlus className="w-5 h-5 text-blue-600" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900">Invite Member</h2>
          </div>
          <form className="flex flex-col gap-4 md:flex-row md:items-end" onSubmit={handleInvite}>
            <div className="flex-1 space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="invite-email">
                <Mail className="w-4 h-4 inline mr-1" />
                Email Address
              </label>
              <input
                id="invite-email"
                name="email"
                type="email"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                placeholder="staff@example.com"
                required
              />
            </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="invite-role">
                <Shield className="w-4 h-4 inline mr-1" />
                Role
              </label>
              <select
                id="invite-role"
                name="role"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              >
                <option value="ADMIN">ADMIN</option>
                <option value="STAFF">STAFF</option>
                <option value="VIEWER">VIEWER</option>
              </select>
            </div>
            <button
              type="submit"
              className="flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
              disabled={inviteMutation.isPending || readOnly}
            >
              <UserPlus className="w-4 h-4" />
              <span>{inviteMutation.isPending ? "Inviting..." : "Invite"}</span>
            </button>
          </form>
        </div>

        {/* Members Table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
                <tr>
                  <Header label="Name" />
                  <Header label="Email" />
                  <Header label="Role" />
                  <Header label="Actions" align="right" />
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-6 py-12 text-center">
                      <div className="flex flex-col items-center">
                        <Users className="w-12 h-12 text-gray-400 mb-3" />
                        <p className="text-sm font-medium text-gray-900 mb-1">No members yet</p>
                        <p className="text-xs text-gray-500">Invite your first team member to get started</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  users.map((user) => (
                    <tr key={user.id} className="hover:bg-gray-50 transition-colors">
                      <Cell>
                        <div className="text-sm font-medium text-gray-900">{user.name || "—"}</div>
                      </Cell>
                      <Cell>
                        <div className="text-sm text-gray-600">{user.email}</div>
                      </Cell>
                      <Cell>
                        {selectedId === user.id ? (
                          <select
                            defaultValue={user.role}
                            onChange={(event) =>
                              updateMutation.mutate({ id: user.id, role: event.target.value as Membership["role"] })
                            }
                            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                          >
                            <option value="OWNER">OWNER</option>
                            <option value="ADMIN">ADMIN</option>
                            <option value="STAFF">STAFF</option>
                            <option value="VIEWER">VIEWER</option>
                          </select>
                        ) : (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                            {user.role}
                          </span>
                        )}
                      </Cell>
                      <Cell align="right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-blue-600 hover:bg-blue-50 disabled:opacity-50 transition-colors"
                            onClick={() => setSelectedId(selectedId === user.id ? null : user.id)}
                            disabled={readOnly}
                          >
                            <Edit className="w-3.5 h-3.5" />
                            <span>{selectedId === user.id ? "Close" : "Change Role"}</span>
                          </button>
                          <button
                            type="button"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors"
                            onClick={() => {
                              if (readOnly) {
                                setError("Cannot remove members while impersonating.");
                                return;
                              }
                              removeMutation.mutate(user.id);
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
    EMAIL_REQUIRED: "Email is required.",
    INVITE_ALREADY_ACCEPTED: "This invitation was already accepted.",
  };
  return map[code] ?? code.replace(/_/g, " ");
}
