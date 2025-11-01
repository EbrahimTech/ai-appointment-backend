"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { z } from "zod";

type Appointment = {
  id: number;
  service_code: string;
  start_at: string;
  end_at: string;
  status: string;
  external_event_id: string | null;
  sync_state: "ok" | "tentative" | "failed";
};

type AppointmentListResponse = {
  items: Appointment[];
  page: number;
  size: number;
  total: number;
};

const createSchema = z.object({
  patient_id: z.number().int().positive(),
  service_code: z.string().min(1),
  start_at_iso: z.string().min(1),
});

const rescheduleSchema = z.object({
  id: z.number().int().positive(),
  new_start_at_iso: z.string().min(1),
});

const cancelSchema = z.object({
  id: z.number().int().positive(),
});

export default function AppointmentsPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const queryClient = useQueryClient();
  const { support } = useSupportSession();
  const readOnly = Boolean(support);

  const [filters, setFilters] = useState({
    from: "",
    to: "",
    page: 1,
    size: 20,
  });

  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const appointmentsQuery = useQuery({
    queryKey: ["appointments", slug, filters],
    queryFn: async () => {
      const search = new URLSearchParams();
      Object.entries(filters).forEach(([key, value]) => {
        if (value) search.set(key, String(value));
      });
      const response = await fetch(`/api/proxy/clinic/${slug}/appointments?${search.toString()}`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load appointments");
      }
      return payload.data as AppointmentListResponse;
    },
  });

  const createMutation = useMutation({
    mutationFn: async (payload: z.infer<typeof createSchema>) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/appointments/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "CREATE_FAILED");
      }
      return result.data as { appointment: Appointment; google_tentative?: boolean };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["appointments", slug] });
      setFeedback(
        `Appointment created. Sync status: ${data.appointment.sync_state}${
          data.google_tentative ? " (Google sync pending)" : ""
        }`
      );
      setError(null);
    },
    onError: (err: Error) => {
      setError(humanizeError(err.message));
      setFeedback(null);
    },
  });

  const rescheduleMutation = useMutation({
    mutationFn: async (payload: z.infer<typeof rescheduleSchema>) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/appointments/reschedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "RESCHEDULE_FAILED");
      }
      return result.data as { appointment: Appointment; google_tentative?: boolean };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["appointments", slug] });
      setFeedback(
        `Appointment rescheduled. Sync status: ${data.appointment.sync_state}${
          data.google_tentative ? " (Google sync pending)" : ""
        }`
      );
      setError(null);
    },
    onError: (err: Error) => {
      setError(humanizeError(err.message));
      setFeedback(null);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: async (payload: z.infer<typeof cancelSchema>) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/appointments/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "CANCEL_FAILED");
      }
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["appointments", slug] });
      setFeedback("Appointment cancelled.");
      setError(null);
    },
    onError: (err: Error) => {
      setError(humanizeError(err.message));
      setFeedback(null);
    },
  });

  const appointments = useMemo(() => appointmentsQuery.data?.items ?? [], [appointmentsQuery.data]);

  function updateFilter(event: React.ChangeEvent<HTMLInputElement>) {
    const { name, value } = event.target;
    setFilters((prev) => ({
      ...prev,
      [name]: value,
      page: 1,
    }));
  }

  function changePage(page: number) {
    setFilters((prev) => ({ ...prev, page }));
  }

  function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly) {
      setError("Cannot modify appointments while impersonating. End support session first.");
      setFeedback(null);
      return;
    }
    const formData = new FormData(event.currentTarget);
    const payload = {
      patient_id: Number(formData.get("patient_id")),
      service_code: String(formData.get("service_code")),
      start_at_iso: String(formData.get("start_at_iso")),
    };
    const parsed = createSchema.safeParse(payload);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid form");
      setFeedback(null);
      return;
    }
    createMutation.mutate(parsed.data);
    event.currentTarget.reset();
  }

  function handleReschedule(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly) {
      setError("Cannot modify appointments while impersonating. End support session first.");
      setFeedback(null);
      return;
    }
    const formData = new FormData(event.currentTarget);
    const payload = {
      id: Number(formData.get("id")),
      new_start_at_iso: String(formData.get("new_start_at_iso")),
    };
    const parsed = rescheduleSchema.safeParse(payload);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid form");
      setFeedback(null);
      return;
    }
    rescheduleMutation.mutate(parsed.data);
    event.currentTarget.reset();
  }

  function handleCancel(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly) {
      setError("Cannot modify appointments while impersonating. End support session first.");
      setFeedback(null);
      return;
    }
    const formData = new FormData(event.currentTarget);
    const payload = { id: Number(formData.get("id")) };
    const parsed = cancelSchema.safeParse(payload);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid form");
      setFeedback(null);
      return;
    }
    cancelMutation.mutate(parsed.data);
    event.currentTarget.reset();
  }

  if (appointmentsQuery.isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading appointments...</p>
      </main>
    );
  }

  if (appointmentsQuery.isError || !appointmentsQuery.data) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Unable to load appointments.</p>
          <button
            type="button"
            onClick={() => appointmentsQuery.refetch()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  const pagination = appointmentsQuery.data;

  return (
    <main className="space-y-8 px-6 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Appointments</h1>
          <p className="text-sm text-muted-foreground">Manage bookings and monitor calendar sync.</p>
        </div>
        <button
          type="button"
          onClick={() => appointmentsQuery.refetch()}
          className="rounded-md border px-3 py-2 text-sm"
        >
          Refresh
        </button>
      </header>
      {readOnly ? (
        <div className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          You are impersonating a clinic. Appointment changes are disabled until the support session ends.
        </div>
      ) : null}

      {feedback ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {feedback}
        </div>
      ) : null}
      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      ) : null}

      <section className="rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Filters</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-3">
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="from">
              From
            </label>
            <input
              id="from"
              name="from"
              type="datetime-local"
              value={filters.from}
              onChange={updateFilter}
              className="w-full rounded border px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="to">
              To
            </label>
            <input
              id="to"
              name="to"
              type="datetime-local"
              value={filters.to}
              onChange={updateFilter}
              className="w-full rounded border px-3 py-2 text-sm"
            />
          </div>
        </div>
      </section>

      <section className="rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Create appointment</h2>
        <form className="mt-4 grid gap-4 md:grid-cols-3" onSubmit={handleCreate}>
          <InputField name="patient_id" label="Patient ID" placeholder="123" type="number" />
          <InputField name="service_code" label="Service code" placeholder="clean" />
          <div className="space-y-1 md:col-span-1">
            <label className="text-sm font-medium" htmlFor="start_at_iso">
              Start (ISO)
            </label>
            <input
              id="start_at_iso"
              name="start_at_iso"
              type="datetime-local"
              className="w-full rounded border px-3 py-2 text-sm"
              required
            />
          </div>
          <div className="md:col-span-3">
            <button
              type="submit"
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              disabled={createMutation.isPending || readOnly}
            >
              {createMutation.isPending ? "Creating..." : "Create appointment"}
            </button>
          </div>
        </form>
      </section>

      <section className="rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Reschedule appointment</h2>
        <form className="mt-4 grid gap-4 md:grid-cols-3" onSubmit={handleReschedule}>
          <InputField name="id" label="Appointment ID" placeholder="456" type="number" />
          <div className="space-y-1 md:col-span-2">
            <label className="text-sm font-medium" htmlFor="new_start_at_iso">
              New start (ISO)
            </label>
            <input
              id="new_start_at_iso"
              name="new_start_at_iso"
              type="datetime-local"
              className="w-full rounded border px-3 py-2 text-sm"
              required
            />
          </div>
          <div className="md:col-span-3">
            <button
              type="submit"
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              disabled={rescheduleMutation.isPending || readOnly}
            >
              {rescheduleMutation.isPending ? "Rescheduling..." : "Reschedule"}
            </button>
          </div>
        </form>
      </section>

      <section className="rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Cancel appointment</h2>
        <form className="mt-4 grid gap-4 md:grid-cols-3" onSubmit={handleCancel}>
          <InputField name="id" label="Appointment ID" placeholder="456" type="number" />
          <div className="md:col-span-3">
            <button
              type="submit"
              className="rounded-md bg-destructive px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              disabled={cancelMutation.isPending || readOnly}
            >
              {cancelMutation.isPending ? "Cancelling..." : "Cancel appointment"}
            </button>
          </div>
        </form>
      </section>

      <section className="overflow-hidden rounded-lg border bg-white shadow-sm">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-secondary/40">
            <tr>
              <Header label="ID" />
              <Header label="Service" />
              <Header label="Start" />
              <Header label="End" />
              <Header label="Status" />
              <Header label="Sync" />
              <Header label="External ID" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {appointments.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-sm text-muted-foreground">
                  No appointments in this range.
                </td>
              </tr>
            ) : (
              appointments.map((appointment) => (
                <tr key={appointment.id} className="hover:bg-secondary/30">
                  <Cell>{appointment.id}</Cell>
                  <Cell>{appointment.service_code}</Cell>
                  <Cell>{formatDate(appointment.start_at)}</Cell>
                  <Cell>{formatDate(appointment.end_at)}</Cell>
                  <Cell>{appointment.status}</Cell>
                  <Cell>
                    <SyncBadge state={appointment.sync_state} />
                  </Cell>
                  <Cell>{appointment.external_event_id ?? "—"}</Cell>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {pagination.total > pagination.size ? (
        <PaginationControls
          current={pagination.page}
          size={pagination.size}
          total={pagination.total}
          onChange={changePage}
        />
      ) : null}
    </main>
  );
}

function Header({ label }: { label: string }) {
  return (
    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
      {label}
    </th>
  );
}

function Cell({ children }: { children: React.ReactNode }) {
  return <td className="whitespace-nowrap px-4 py-3 text-sm">{children}</td>;
}

function SyncBadge({ state }: { state: Appointment["sync_state"] }) {
  const styles: Record<Appointment["sync_state"], string> = {
    ok: "bg-emerald-100 text-emerald-700",
    tentative: "bg-amber-100 text-amber-700",
    failed: "bg-red-100 text-red-700",
  };
  const labels: Record<Appointment["sync_state"], string> = {
    ok: "Synced",
    tentative: "Sync pending",
    failed: "Sync failed",
  };
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${styles[state]}`}>{labels[state]}</span>;
}

function PaginationControls({
  current,
  size,
  total,
  onChange,
}: {
  current: number;
  size: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const maxPage = Math.ceil(total / size);
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">
        Page {current} of {maxPage}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="rounded border px-3 py-1 text-sm disabled:opacity-50"
          onClick={() => onChange(Math.max(1, current - 1))}
          disabled={current <= 1}
        >
          Previous
        </button>
        <button
          type="button"
          className="rounded border px-3 py-1 text-sm disabled:opacity-50"
          onClick={() => onChange(Math.min(maxPage, current + 1))}
          disabled={current >= maxPage}
        >
          Next
        </button>
      </div>
    </div>
  );
}

function InputField({
  name,
  label,
  placeholder,
  type = "text",
}: {
  name: string;
  label: string;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium" htmlFor={name}>
        {label}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        placeholder={placeholder}
        className="w-full rounded border px-3 py-2 text-sm"
        required
      />
    </div>
  );
}

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function humanizeError(code: string | undefined) {
  if (!code) return "Something went wrong.";
  const map: Record<string, string> = {
    SLOT_TAKEN: "The selected slot is already taken. Please choose another time.",
    INVALID_SERVICE: "Invalid service code. Please verify the service code.",
    OUT_OF_HOURS: "Selected time is outside working hours.",
    NO_HSM_AVAILABLE: "No approved template is available to contact the patient.",
    RATE_LIMIT: "Too many requests. Please wait a moment.",
  };
  return map[code] ?? code.replace(/_/g, " ");
}
