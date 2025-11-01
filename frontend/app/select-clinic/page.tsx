"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

type Clinic = {
  slug: string;
  role: string;
};

export default function SelectClinicPage() {
  const t = useTranslations("selectClinic");
  const router = useRouter();
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [selected, setSelected] = useState<string>("");

  useEffect(() => {
    (async () => {
      const response = await fetch("/api/session/me");
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      const data = await response.json();
      if (data?.data?.clinics?.length) {
        setClinics(data.data.clinics);
      } else {
        router.replace("/login");
      }
    })().catch(() => router.replace("/login"));
  }, [router]);

  async function handleContinue() {
    if (!selected) return;
    const response = await fetch("/api/session/select-clinic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: selected }),
    });
    if (response.ok) {
      router.replace(`/c/${selected}/dashboard`);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-md space-y-4 rounded-lg border bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold">{t("title")}</h1>
        <div className="space-y-2">
          {clinics.map((clinic) => (
            <label key={clinic.slug} className="flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2">
              <input
                type="radio"
                name="clinic"
                value={clinic.slug}
                checked={selected === clinic.slug}
                onChange={() => setSelected(clinic.slug)}
              />
              <span className="text-sm font-medium">
                {clinic.slug} · {clinic.role}
              </span>
            </label>
          ))}
        </div>
        <button
          type="button"
          onClick={handleContinue}
          disabled={!selected}
          className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {t("button")}
        </button>
      </div>
    </main>
  );
}
