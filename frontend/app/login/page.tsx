"use client";

import { useState, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});

type LoginInput = z.infer<typeof loginSchema>;
type LoginResponse = {
  clinics: { slug: string; role: string }[];
  hq_role?: string | null;
};

export default function LoginPage() {
  const t = useTranslations("login");
  const router = useRouter();
  const searchParams = useSearchParams();
  const accepted = useMemo(() => searchParams.get("accepted") === "1", [searchParams]);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation<LoginResponse, Error, LoginInput>({
    mutationFn: async (values) => {
      const response = await fetch("/api/session/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "LOGIN_FAILED");
      }
      return result.data as LoginResponse;
    },
    onSuccess: (data) => {
      setError(null);
      if (data.hq_role) {
        router.push("/hq");
        return;
      }
      if (data.clinics?.length) {
        router.push("/select-clinic");
      } else {
        router.refresh();
      }
    },
    onError: () => {
      setError(t("error"));
    },
  });

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const values: LoginInput = {
      email: String(formData.get("email") || ""),
      password: String(formData.get("password") || ""),
    };
    const parsed = loginSchema.safeParse(values);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? t("error"));
      return;
    }
    mutation.mutate(parsed.data);
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-lg border bg-white p-6 shadow-sm">
        <h1 className="mb-4 text-2xl font-semibold">{t("title")}</h1>
        {accepted ? (
          <p className="mb-4 rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
            Invitation accepted. Please login with your new password.
          </p>
        ) : null}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-1">
            <label htmlFor="email" className="text-sm font-medium">
              {t("email")}
            </label>
            <input
              id="email"
              name="email"
              type="email"
              className="w-full rounded-md border px-3 py-2 text-sm"
              required
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="password" className="text-sm font-medium">
              {t("password")}
            </label>
            <input
              id="password"
              name="password"
              type="password"
              className="w-full rounded-md border px-3 py-2 text-sm"
              required
            />
          </div>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
            <button
              type="submit"
              disabled={mutation.isPending}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              {mutation.isPending ? "..." : t("submit")}
            </button>
        </form>
      </div>
    </main>
  );
}
