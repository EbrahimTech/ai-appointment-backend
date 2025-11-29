"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Building2, CheckCircle2, ArrowRight, Loader2 } from "lucide-react";

type Clinic = {
  slug: string;
  role: string;
};

export default function SelectClinicPage() {
  const t = useTranslations("selectClinic");
  const router = useRouter();
  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
      const response = await fetch("/api/session/me");
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      const data = await response.json();
      if (data?.data?.clinics?.length) {
        setClinics(data.data.clinics);
          // Auto-select if only one clinic
          if (data.data.clinics.length === 1) {
            setSelected(data.data.clinics[0].slug);
          }
      } else {
          router.replace("/login");
        }
      } catch (error) {
        router.replace("/login");
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  async function handleContinue() {
    if (!selected || submitting) return;
    try {
      setSubmitting(true);
    const response = await fetch("/api/session/select-clinic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug: selected }),
    });
    if (response.ok) {
      router.replace(`/c/${selected}/dashboard`);
    }
    } catch (error) {
      // Handle error
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading clinics...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center w-16 h-16 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg mx-auto mb-4">
            <Building2 className="w-8 h-8" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">{t("title")}</h1>
          <p className="text-sm text-gray-600">Select a clinic to continue</p>
        </div>

        {/* Clinic Selection Card */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-lg overflow-hidden">
          <div className="p-6">
            {clinics.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-sm text-gray-500">No clinics available</p>
              </div>
            ) : (
              <div className="space-y-3">
                {clinics.map((clinic) => {
                  const isSelected = selected === clinic.slug;
                  return (
                    <label
                      key={clinic.slug}
                      className={`
                        flex items-center gap-4 p-4 rounded-lg border-2 cursor-pointer transition-all
                        ${
                          isSelected
                            ? "border-blue-500 bg-blue-50 shadow-sm"
                            : "border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50"
                        }
                      `}
                    >
                      <div className="flex-shrink-0">
                        {isSelected ? (
                          <div className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-600 text-white">
                            <CheckCircle2 className="w-4 h-4" />
                          </div>
                        ) : (
                          <div className="w-6 h-6 rounded-full border-2 border-gray-300"></div>
                        )}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <Building2 className={`w-4 h-4 ${isSelected ? "text-blue-600" : "text-gray-400"}`} />
                          <span className={`text-base font-semibold ${isSelected ? "text-gray-900" : "text-gray-700"}`}>
                            {clinic.slug}
                          </span>
                        </div>
                        <span className={`text-xs ${isSelected ? "text-blue-600" : "text-gray-500"}`}>
                          {clinic.role}
                        </span>
                      </div>
              <input
                type="radio"
                name="clinic"
                value={clinic.slug}
                        checked={isSelected}
                onChange={() => setSelected(clinic.slug)}
                        className="sr-only"
              />
            </label>
                  );
                })}
              </div>
            )}
        </div>

          {/* Continue Button */}
          <div className="px-6 pb-6 pt-4 border-t border-gray-200">
        <button
          type="button"
          onClick={handleContinue}
              disabled={!selected || submitting}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-6 py-3 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
        >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Loading...</span>
                </>
              ) : (
                <>
                  <span>{t("button")}</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
        </button>
          </div>
        </div>
      </div>
    </div>
  );
}
