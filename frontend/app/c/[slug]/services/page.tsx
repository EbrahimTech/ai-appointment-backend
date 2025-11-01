"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { z } from "zod";

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
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading services...</p>
      </main>
    );
  }

  if (servicesQuery.isError || hoursQuery.isError) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Unable to load services or hours.</p>
          <button
            type="button"
            onClick={() => {
              servicesQuery.refetch();
              hoursQuery.refetch();
            }}
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
        <h1 className="text-2xl font-semibold">Services & Hours</h1>
        <p className="text-sm text-muted-foreground">
          Configure services offered by the clinic and their availability windows.
        </p>
      </header>
      {readOnly ? (
        <div className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          You are impersonating a clinic. Service changes are disabled until the support session ends.
        </div>
      ) : null}

      {feedback ? (
        <div className="rounded border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{feedback}</div>
      ) : null}
      {error ? (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      ) : null}

      <section className="space-y-4 rounded-lg border bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Services</h2>
          <form onSubmit={handleServicesSubmit} className="hidden" id="services-form">
            <input type="hidden" name="rows" value={services.length} />
          </form>
          <button
            type="button"
            onClick={() => updateServices.mutate({ services: [] })}
            className="hidden"
          />
        </div>
        <form className="space-y-4" onSubmit={handleServicesSubmit}>
          <input type="hidden" name="rows" value={services.length} />
          {services.map((service, index) => (
            <div key={service.code} className="rounded border px-4 py-3">
              <div className="grid gap-4 md:grid-cols-3">
                <Field label="Code">
                  <input
                    name={`service_code_${index}`}
                    defaultValue={service.code}
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                  />
                </Field>
                <Field label="Name">
                  <input
                    name={`service_name_${index}`}
                    defaultValue={service.name}
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                  />
                </Field>
                <Field label="Duration (minutes)">
                  <input
                    name={`service_duration_${index}`}
                    type="number"
                    defaultValue={service.duration_minutes}
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                  />
                </Field>
                <Field label="Language">
                  <input
                    name={`service_lang_${index}`}
                    defaultValue={service.language}
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                  />
                </Field>
                <Field label="Active">
                  <input
                    name={`service_active_${index}`}
                    type="checkbox"
                    defaultChecked={service.is_active}
                    className="h-4 w-4"
                  />
                </Field>
                <Field label="Description" className="md:col-span-3">
                  <textarea
                    name={`service_desc_${index}`}
                    defaultValue={service.description}
                    className="w-full rounded border px-3 py-2 text-sm"
                  />
                </Field>
              </div>
            </div>
          ))}
          <button
            type="submit"
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            disabled={updateServices.isPending || readOnly}
          >
            {updateServices.isPending ? "Saving..." : "Save services"}
          </button>
        </form>
      </section>

      <section className="space-y-4 rounded-lg border bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Service hours</h2>
        </div>
        <form className="space-y-4" onSubmit={handleHoursSubmit}>
          <input type="hidden" name="rows_hours" value={hours.length} />
          {hours.map((hour, index) => (
            <div key={`${hour.service_code}-${hour.weekday}-${index}`} className="rounded border px-4 py-3">
              <div className="grid gap-4 md:grid-cols-4">
                <Field label="Service code">
                  <input
                    name={`hour_service_${index}`}
                    defaultValue={hour.service_code}
                    className="w-full rounded border px-3 py-2 text-sm"
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
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                  />
                </Field>
                <Field label="Start time (HH:MM)">
                  <input
                    name={`hour_start_${index}`}
                    defaultValue={hour.start_time}
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                  />
                </Field>
                <Field label="End time (HH:MM)">
                  <input
                    name={`hour_end_${index}`}
                    defaultValue={hour.end_time}
                    className="w-full rounded border px-3 py-2 text-sm"
                    required
                  />
                </Field>
              </div>
            </div>
          ))}
          <button
            type="submit"
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            disabled={updateHours.isPending || readOnly}
          >
            {updateHours.isPending ? "Saving..." : "Save hours"}
          </button>
        </form>
      </section>
    </main>
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
    <div className={`space-y-1 ${className ?? ""}`}>
      <label className="text-sm font-medium">{label}</label>
      {children}
    </div>
  );
}
