"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { z } from "zod";
import { Settings, Clock, RefreshCw, Save, AlertCircle, CheckCircle2, X, Plus } from "lucide-react";

type Service = {
  code: string;
  name: string;
  description: string;
  duration_minutes: number;
  language: string;
  is_active: boolean;
};

type ServiceHours = {
  service_code: string;
  weekday: number;
  start_time: string;
  end_time: string;
};

const serviceSchema = z.object({
  services: z.array(
    z.object({
      code: z.string().min(1),
      name: z.string().min(1),
      description: z.string().optional(),
      duration_minutes: z.number().int().positive(),
      language: z.string().min(1),
      is_active: z.boolean(),
    })
  ),
});

const hoursSchema = z.object({
  hours: z.array(
    z.object({
      service_code: z.string().min(1),
      weekday: z.number().int().min(0).max(6),
      start_time: z.string().min(1),
      end_time: z.string().min(1),
    })
  ),
});

export default function ServicesPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const queryClient = useQueryClient();
  const { support } = useSupportSession();
  const readOnly = Boolean(support);

  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const servicesQuery = useQuery({
    queryKey: ["services", slug],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/services`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load services");
      }
      return payload.data.items as Service[];
    },
  });

  const hoursQuery = useQuery({
    queryKey: ["hours", slug],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/hours`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load hours");
      }
      return payload.data.items as ServiceHours[];
    },
  });

  const updateServices = useMutation({
    mutationFn: async (payload: z.infer<typeof serviceSchema>) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/services`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "UPDATE_FAILED");
      }
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["services", slug] });
      setFeedback("Services updated successfully.");
      setError(null);
    },
    onError: (err: Error) => {
      setError(err.message);
      setFeedback(null);
    },
  });

  const updateHours = useMutation({
    mutationFn: async (payload: z.infer<typeof hoursSchema>) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/hours`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "UPDATE_FAILED");
      }
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["hours", slug] });
      setFeedback("Service hours updated successfully.");
      setError(null);
    },
    onError: (err: Error) => {
      setError(err.message);
      setFeedback(null);
    },
  });

  const services = useMemo(() => servicesQuery.data ?? [], [servicesQuery.data]);
  const hours = useMemo(() => hoursQuery.data ?? [], [hoursQuery.data]);

  function handleServicesSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly) {
      setError("Cannot modify services while impersonating. End support session first.");
      setFeedback(null);
      return;
    }
    const formData = new FormData(event.currentTarget);
    const count = Number(formData.get("rows")) || 0;
    const payload = {
      services: Array.from({ length: count }).map((_, index) => ({
        code: String(formData.get(`service_code_${index}`) || ""),
        name: String(formData.get(`service_name_${index}`) || ""),
        description: String(formData.get(`service_desc_${index}`) || ""),
        duration_minutes: Number(formData.get(`service_duration_${index}`) || 0),
        language: String(formData.get(`service_lang_${index}`) || ""),
        is_active: formData.get(`service_active_${index}`) === "on",
      })),
    };
    const parsed = serviceSchema.safeParse(payload);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid service data");
      setFeedback(null);
      return;
    }
    updateServices.mutate(parsed.data);
  }

  function handleHoursSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly) {
      setError("Cannot modify service hours while impersonating. End support session first.");
      setFeedback(null);
      return;
    }
    const formData = new FormData(event.currentTarget);
    const count = Number(formData.get("rows_hours")) || 0;
    const payload = {
      hours: Array.from({ length: count }).map((_, index) => ({
        service_code: String(formData.get(`hour_service_${index}`) || ""),
        weekday: Number(formData.get(`hour_weekday_${index}`) || 0),
        start_time: String(formData.get(`hour_start_${index}`) || ""),
        end_time: String(formData.get(`hour_end_${index}`) || ""),
      })),
    };
    const parsed = hoursSchema.safeParse(payload);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid hours data");
      setFeedback(null);
      return;
    }
    updateHours.mutate(parsed.data);
  }

  if (servicesQuery.isPending || hoursQuery.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading services...</p>
        </div>
      </div>
    );
  }

  if (servicesQuery.isError || hoursQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-4">
          <div className="flex items-center justify-center w-16 h-16 rounded-full bg-red-100 mx-auto">
            <Settings className="w-8 h-8 text-red-600" />
          </div>
          <div>
            <p className="text-base font-medium text-gray-900 mb-1">Unable to load services</p>
            <p className="text-sm text-gray-500 mb-4">Please try again</p>
          </div>
          <button
            type="button"
            onClick={() => {
              servicesQuery.refetch();
              hoursQuery.refetch();
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
            <div className="flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-lg">
              <Settings className="w-7 h-7" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">Services & Hours</h1>
              <p className="text-sm text-gray-600">Configure services offered by the clinic and their availability windows</p>
            </div>
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
                You are impersonating a clinic. Service changes are disabled until the support session ends.
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
            <X className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
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

        {/* Services Section */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-indigo-100">
              <Settings className="w-5 h-5 text-indigo-600" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900">Services</h2>
          </div>
          <form className="space-y-4" onSubmit={handleServicesSubmit}>
            <input type="hidden" name="rows" value={services.length} />
            {services.map((service, index) => (
              <div key={service.code} className="rounded-lg border border-gray-200 bg-gray-50 px-5 py-4">
                <div className="grid gap-4 md:grid-cols-3">
                  <Field label="Code">
                    <input
                      name={`service_code_${index}`}
                      defaultValue={service.code}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      required
                    />
                  </Field>
                  <Field label="Name">
                    <input
                      name={`service_name_${index}`}
                      defaultValue={service.name}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      required
                    />
                  </Field>
                  <Field label="Duration (minutes)">
                    <input
                      name={`service_duration_${index}`}
                      type="number"
                      defaultValue={service.duration_minutes}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      required
                    />
                  </Field>
                  <Field label="Language">
                    <input
                      name={`service_lang_${index}`}
                      defaultValue={service.language}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      required
                    />
                  </Field>
                  <Field label="Active">
                    <div className="flex items-center">
                      <input
                        name={`service_active_${index}`}
                        type="checkbox"
                        defaultChecked={service.is_active}
                        className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                    </div>
                  </Field>
                  <Field label="Description" className="md:col-span-3">
                    <textarea
                      name={`service_desc_${index}`}
                      defaultValue={service.description}
                      rows={2}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    />
                  </Field>
                </div>
              </div>
            ))}
            <button
              type="submit"
              className="flex items-center gap-2 rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
              disabled={updateServices.isPending || readOnly}
            >
              <Save className="w-4 h-4" />
              <span>{updateServices.isPending ? "Saving..." : "Save Services"}</span>
            </button>
          </form>
        </div>

        {/* Service Hours Section */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex items-center gap-3 mb-6">
            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-purple-100">
              <Clock className="w-5 h-5 text-purple-600" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900">Service Hours</h2>
          </div>
          <form className="space-y-4" onSubmit={handleHoursSubmit}>
            <input type="hidden" name="rows_hours" value={hours.length} />
            {hours.map((hour, index) => (
              <div key={`${hour.service_code}-${hour.weekday}-${index}`} className="rounded-lg border border-gray-200 bg-gray-50 px-5 py-4">
                <div className="grid gap-4 md:grid-cols-4">
                  <Field label="Service Code">
                    <input
                      name={`hour_service_${index}`}
                      defaultValue={hour.service_code}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      required
                    />
                  </Field>
                  <Field label="Weekday (0=Mon)">
                    <input
                      name={`hour_weekday_${index}`}
                      type="number"
                      min={0}
                      max={6}
                      defaultValue={hour.weekday}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      required
                    />
                  </Field>
                  <Field label="Start Time (HH:MM)">
                    <input
                      name={`hour_start_${index}`}
                      defaultValue={hour.start_time}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      required
                    />
                  </Field>
                  <Field label="End Time (HH:MM)">
                    <input
                      name={`hour_end_${index}`}
                      defaultValue={hour.end_time}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      required
                    />
                  </Field>
                </div>
              </div>
            ))}
            <button
              type="submit"
              className="flex items-center gap-2 rounded-lg bg-purple-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 transition-colors shadow-sm"
              disabled={updateHours.isPending || readOnly}
            >
              <Save className="w-4 h-4" />
              <span>{updateHours.isPending ? "Saving..." : "Save Hours"}</span>
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className ?? ""}`}>
      <label className="block text-sm font-medium text-gray-700">{label}</label>
      {children}
    </div>
  );
}
