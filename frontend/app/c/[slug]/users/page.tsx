"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { z } from "zod";

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
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading users...</p>
      </main>
    );
  }

  if (usersQuery.isError) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Unable to load users.</p>
          <button
            type="button"
            onClick={() => usersQuery.refetch()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="space-y-8 px-6 py-8">
      <header>
        <h1 className="text-2xl font-semibold">Clinic members</h1>
        <p className="text-sm text-muted-foreground">Invite staff and manage access roles.</p>
      </header>
      {readOnly ? (
        <div className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          You are impersonating a clinic. Member management is disabled until the support session ends.
        </div>
      ) : null}

      {feedback ? (
        <div className="rounded border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{feedback}</div>
      ) : null}
      {error ? (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      ) : null}

      <section className="rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Invite member</h2>
        <form className="mt-4 flex flex-col gap-4 md:flex-row" onSubmit={handleInvite}>
          <div className="flex-1 space-y-1">
            <label className="text-sm font-medium" htmlFor="invite-email">
              Email
            </label>
            <input
              id="invite-email"
              name="email"
              type="email"
              className="w-full rounded border px-3 py-2 text-sm"
              placeholder="staff@example.com"
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="invite-role">
              Role
            </label>
            <select id="invite-role" name="role" className="w-full rounded border px-3 py-2 text-sm">
              <option value="ADMIN">ADMIN</option>
              <option value="STAFF">STAFF</option>
              <option value="VIEWER">VIEWER</option>
            </select>
          </div>
          <button
            type="submit"
            className="self-end rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            disabled={inviteMutation.isPending || readOnly}
          >
            {inviteMutation.isPending ? "Inviting..." : "Invite"}
          </button>
        </form>
      </section>

      <section className="overflow-hidden rounded-lg border bg-white shadow-sm">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-secondary/40">
            <tr>
              <Header label="Name" />
              <Header label="Email" />
              <Header label="Role" />
              <Header label="Actions" align="right" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {users.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-sm text-muted-foreground">
                  No members yet.
                </td>
              </tr>
            ) : (
              users.map((user) => (
                <tr key={user.id}>
                  <Cell>{user.name || "—"}</Cell>
                  <Cell>{user.email}</Cell>
                  <Cell>
                    {selectedId === user.id ? (
                      <select
                        defaultValue={user.role}
                        onChange={(event) =>
                          updateMutation.mutate({ id: user.id, role: event.target.value as Membership["role"] })
                        }
                        className="rounded border px-2 py-1 text-sm"
                      >
                        <option value="OWNER">OWNER</option>
                        <option value="ADMIN">ADMIN</option>
                        <option value="STAFF">STAFF</option>
                        <option value="VIEWER">VIEWER</option>
                      </select>
                    ) : (
                      <span className="text-sm font-medium">{user.role}</span>
                    )}
                  </Cell>
                  <Cell align="right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        className="rounded border px-3 py-1 text-xs disabled:opacity-50"
                        onClick={() => setSelectedId(selectedId === user.id ? null : user.id)}
                        disabled={readOnly}
                      >
                        {selectedId === user.id ? "Close" : "Change role"}
                      </button>
                      <button
                        type="button"
                        className="rounded border px-3 py-1 text-xs text-red-600"
                        onClick={() => {
                          if (readOnly) {
                            setError("Cannot remove members while impersonating.");
                            return;
                          }
                          removeMutation.mutate(user.id);
                        }}
                        disabled={removeMutation.isPending || readOnly}
                      >
                        Remove
                      </button>
                    </div>
                  </Cell>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </main>
  );
}

function Header({ label, align = "left" }: { label: string; align?: "left" | "right" }) {
  return (
    <th className={`px-4 py-3 text-xs font-semibold uppercase text-muted-foreground ${align === "right" ? "text-right" : "text-left"}`}>
      {label}
    </th>
  );
}

function Cell({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return <td className={`px-4 py-3 text-sm ${align === "right" ? "text-right" : ""}`}>{children}</td>;
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
