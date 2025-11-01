"use client";

import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";

const inviteSchema = z
  .object({
    password: z.string().min(8),
    confirmPassword: z.string().min(8),
    first_name: z.string().optional(),
    last_name: z.string().optional(),
  })
  .refine((values) => values.password === values.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

type InviteInput = z.infer<typeof inviteSchema>;

export default function AcceptInvitePage() {
  const params = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const token = useMemo(() => params.get("token") ?? "", [params]);

  const mutation = useMutation({
    mutationFn: async (values: InviteInput) => {
      const response = await fetch("/api/session/accept-invite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          password: values.password,
          first_name: values.first_name,
          last_name: values.last_name,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "UNKNOWN_ERROR");
      }
      return payload;
    },
    onSuccess: () => {
      router.replace("/login?accepted=1");
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  if (!token) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <div className="w-full max-w-md rounded-lg border bg-white p-6 shadow-sm">
          <h1 className="text-xl font-semibold">Invitation</h1>
          <p className="mt-3 text-sm text-red-600">Invalid invitation token.</p>
        </div>
      </main>
    );
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const values: InviteInput = {
      password: String(formData.get("password") || ""),
      confirmPassword: String(formData.get("confirmPassword") || ""),
      first_name: String(formData.get("first_name") || "") || undefined,
      last_name: String(formData.get("last_name") || "") || undefined,
    };
    const parsed = inviteSchema.safeParse(values);
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      setError(issue?.message ?? "Invalid form");
      return;
    }
    setError(null);
    mutation.mutate(parsed.data);
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md rounded-lg border bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold">Accept Invite</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Set your password to activate your clinic owner account.
        </p>
        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              className="w-full rounded border px-3 py-2 text-sm"
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="confirmPassword">
              Confirm password
            </label>
            <input
              id="confirmPassword"
              name="confirmPassword"
              type="password"
              className="w-full rounded border px-3 py-2 text-sm"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="first_name">
                First name (optional)
              </label>
              <input id="first_name" name="first_name" className="w-full rounded border px-3 py-2 text-sm" />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="last_name">
                Last name (optional)
              </label>
              <input id="last_name" name="last_name" className="w-full rounded border px-3 py-2 text-sm" />
            </div>
          </div>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <button
            type="submit"
            disabled={mutation.isPending}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {mutation.isPending ? "Submitting..." : "Activate"}
          </button>
        </form>
      </div>
    </main>
  );
}
