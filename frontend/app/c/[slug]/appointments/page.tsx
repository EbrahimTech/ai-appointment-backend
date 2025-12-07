"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { z } from "zod";
import { Calendar, RefreshCw, Plus, Edit, XCircle, Filter, AlertCircle, CheckCircle2, X, Search, Info, Clock } from "lucide-react";

type Appointment = {
  id: number;
  service_code: string;
  start_at: string;
  end_at: string;
  status: string;
  external_event_id: string | null;
  sync_state: "ok" | "tentative" | "failed";
};

type Service = {
  code: string;
  name: string;
  description: string;
  duration_minutes: number;
  language: string;
  is_active: boolean;
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
  const [serviceSearch, setServiceSearch] = useState("");
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [showServiceDropdown, setShowServiceDropdown] = useState(false);

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
      setSelectedService(null);
      setServiceSearch("");
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

  const filteredServices = useMemo(() => {
    const services = servicesQuery.data ?? [];
    if (!serviceSearch) return services;
    const lowerSearch = serviceSearch.toLowerCase();
    return services.filter(
      (s) =>
        s.code.toLowerCase().includes(lowerSearch) ||
        s.name.toLowerCase().includes(lowerSearch)
    );
  }, [servicesQuery.data, serviceSearch]);

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
    if (!selectedService) {
      setError("Please select a service");
      setFeedback(null);
      return;
    }
    const formData = new FormData(event.currentTarget);
    const payload = {
      patient_id: Number(formData.get("patient_id")),
      service_code: selectedService.code,
      start_at_iso: String(formData.get("start_at_iso")),
    };
    console.log("Creating appointment with payload:", payload);
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
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading appointments...</p>
        </div>
      </div>
    );
  }

  if (appointmentsQuery.isError || !appointmentsQuery.data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-4">
          <div className="flex items-center justify-center w-16 h-16 rounded-full bg-red-100 mx-auto">
            <Calendar className="w-8 h-8 text-red-600" />
          </div>
          <div>
            <p className="text-base font-medium text-gray-900 mb-1">Unable to load appointments</p>
            <p className="text-sm text-gray-500 mb-4">Please try again</p>
          </div>
          <button
            type="button"
            onClick={() => appointmentsQuery.refetch()}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            <span>Retry</span>
          </button>
        </div>
      </div>
    );
  }

  const pagination = appointmentsQuery.data;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header Section */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-4">
              <div className="flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br from-green-500 to-emerald-600 text-white shadow-lg">
                <Calendar className="w-7 h-7" />
              </div>
        <div>
                <h1 className="text-3xl font-bold text-gray-900 mb-2">Appointments</h1>
                <p className="text-sm text-gray-600">Manage bookings and monitor calendar synchronization</p>
              </div>
        </div>
        <button
          type="button"
          onClick={() => appointmentsQuery.refetch()}
              disabled={appointmentsQuery.isFetching}
              className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors shadow-sm"
        >
              <RefreshCw className={`w-4 h-4 ${appointmentsQuery.isFetching ? "animate-spin" : ""}`} />
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
                You are impersonating a clinic. Appointment changes are disabled until the support session ends.
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

        {/* Filters Section */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="flex items-center gap-2 mb-4">
            <Filter className="w-5 h-5 text-gray-500" />
            <h2 className="text-lg font-semibold text-gray-900">Filters</h2>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="from">
                <Calendar className="w-4 h-4 inline mr-1" />
                From Date
            </label>
            <input
              id="from"
              name="from"
              type="datetime-local"
              value={filters.from}
              onChange={updateFilter}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            />
          </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="to">
                <Calendar className="w-4 h-4 inline mr-1" />
                To Date
            </label>
            <input
              id="to"
              name="to"
              type="datetime-local"
              value={filters.to}
              onChange={updateFilter}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            />
            </div>
          </div>
        </div>

        {/* Action Forms */}
        <div className="grid gap-6 md:grid-cols-3">
          {/* Create Appointment */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-green-100">
                <Plus className="w-5 h-5 text-green-600" />
              </div>
              <h2 className="text-lg font-semibold text-gray-900">Create</h2>
            </div>
            <form className="space-y-4" onSubmit={handleCreate}>
          <InputField name="patient_id" label="Patient ID" placeholder="123" type="number" />
              
              {/* Service Selector with Search */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700">
                  Service <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type="text"
                      placeholder={selectedService ? `${selectedService.name} (${selectedService.code})` : "Search services..."}
                      value={serviceSearch}
                      onChange={(e) => setServiceSearch(e.target.value)}
                      onFocus={() => setShowServiceDropdown(true)}
                      onBlur={() => setTimeout(() => setShowServiceDropdown(false), 200)}
                      className="w-full rounded-lg border border-gray-300 pl-10 pr-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    />
                  </div>
                  
                  {showServiceDropdown && (
                    <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                      {servicesQuery.isLoading ? (
                        <div className="px-4 py-3 text-sm text-gray-500">Loading services...</div>
                      ) : filteredServices.length === 0 ? (
                        <div className="px-4 py-3 text-sm text-gray-500">No services found</div>
                      ) : (
                        filteredServices.map((service) => (
                          <button
                            key={service.code}
                            type="button"
                            onClick={() => {
                              setSelectedService(service);
                              setServiceSearch("");
                              setShowServiceDropdown(false);
                            }}
                            className="w-full px-4 py-3 text-left hover:bg-gray-50 transition-colors border-b border-gray-100 last:border-0"
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium text-gray-900 truncate">
                                  {service.name}
                                </div>
                                <div className="text-xs text-gray-500 mt-0.5">
                                  Code: {service.code} • {service.duration_minutes} min
                                </div>
                              </div>
                              {selectedService?.code === service.code && (
                                <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0 mt-0.5" />
                              )}
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>
                
                {selectedService && (
                  <div className="flex items-center gap-2 mt-2 p-2 bg-blue-50 rounded-lg">
                    <CheckCircle2 className="w-4 h-4 text-blue-600 flex-shrink-0" />
                    <span className="text-xs text-blue-700 font-medium">
                      {selectedService.name} ({selectedService.code})
                    </span>
                    <button
                      type="button"
                      onClick={() => setSelectedService(null)}
                      className="ml-auto p-0.5 rounded hover:bg-blue-100 transition-colors"
                    >
                      <X className="w-3 h-3 text-blue-600" />
                    </button>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700" htmlFor="start_at_iso">
                  Start Time
            </label>
            <input
              id="start_at_iso"
              name="start_at_iso"
              type="datetime-local"
                  className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              required
            />
                <div className="flex items-start gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <Info className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
                  <div className="text-xs text-blue-800">
                    <p className="font-medium mb-1">Working Hours:</p>
                    <ul className="space-y-0.5 text-blue-700">
                      <li>• Mon-Wed: 9:00 AM - 5:00 PM</li>
                      <li>• Thursday: 9:00 AM - 1:00 PM</li>
                      <li className="text-red-600 font-medium">• Friday: Closed</li>
                      <li>• Saturday: 9:00 AM - 1:00 PM, 2:00 PM - 6:00 PM</li>
                      <li>• Sunday: 9:00 AM - 5:00 PM, 2:00 PM - 8:00 PM</li>
                    </ul>
                  </div>
                </div>
          </div>
            <button
              type="submit"
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-green-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50 transition-colors shadow-sm"
              disabled={createMutation.isPending || readOnly}
            >
                <Plus className="w-4 h-4" />
                <span>{createMutation.isPending ? "Creating..." : "Create Appointment"}</span>
            </button>
            </form>
          </div>

          {/* Reschedule Appointment */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-blue-100">
                <Edit className="w-5 h-5 text-blue-600" />
              </div>
              <h2 className="text-lg font-semibold text-gray-900">Reschedule</h2>
            </div>
            <form className="space-y-4" onSubmit={handleReschedule}>
          <InputField name="id" label="Appointment ID" placeholder="456" type="number" />
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700" htmlFor="new_start_at_iso">
                  New Start Time
            </label>
            <input
              id="new_start_at_iso"
              name="new_start_at_iso"
              type="datetime-local"
                  className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              required
            />
                <div className="flex items-start gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <Clock className="w-4 h-4 text-blue-600 flex-shrink-0 mt-0.5" />
                  <p className="text-xs text-blue-700">Ensure the new time is within working hours (Mon-Thu: 9AM-5PM, Sat-Sun: 9AM-8PM). Friday is closed.</p>
                </div>
          </div>
            <button
              type="submit"
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
              disabled={rescheduleMutation.isPending || readOnly}
            >
                <Edit className="w-4 h-4" />
                <span>{rescheduleMutation.isPending ? "Rescheduling..." : "Reschedule"}</span>
            </button>
            </form>
          </div>

          {/* Cancel Appointment */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <div className="flex items-center gap-2 mb-4">
              <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-red-100">
                <XCircle className="w-5 h-5 text-red-600" />
              </div>
              <h2 className="text-lg font-semibold text-gray-900">Cancel</h2>
            </div>
            <form className="space-y-4" onSubmit={handleCancel}>
          <InputField name="id" label="Appointment ID" placeholder="456" type="number" />
            <button
              type="submit"
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 transition-colors shadow-sm"
              disabled={cancelMutation.isPending || readOnly}
            >
                <XCircle className="w-4 h-4" />
                <span>{cancelMutation.isPending ? "Cancelling..." : "Cancel Appointment"}</span>
            </button>
            </form>
          </div>
        </div>

        {/* Appointments Table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
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
              <tbody className="bg-white divide-y divide-gray-200">
            {appointments.length === 0 ? (
              <tr>
                    <td colSpan={7} className="px-6 py-12 text-center">
                      <div className="flex flex-col items-center">
                        <Calendar className="w-12 h-12 text-gray-400 mb-3" />
                        <p className="text-sm font-medium text-gray-900 mb-1">No appointments found</p>
                        <p className="text-xs text-gray-500">Try adjusting your date filters</p>
                      </div>
                </td>
              </tr>
            ) : (
              appointments.map((appointment) => (
                    <tr key={appointment.id} className="hover:bg-gray-50 transition-colors">
                  <Cell>{appointment.id}</Cell>
                      <Cell>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          {appointment.service_code}
                        </span>
                      </Cell>
                  <Cell>{formatDate(appointment.start_at)}</Cell>
                  <Cell>{formatDate(appointment.end_at)}</Cell>
                      <Cell>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 capitalize">
                          {appointment.status}
                        </span>
                      </Cell>
                  <Cell>
                    <SyncBadge state={appointment.sync_state} />
                  </Cell>
                      <Cell className="font-mono text-xs">{appointment.external_event_id ?? "—"}</Cell>
                </tr>
              ))
            )}
          </tbody>
        </table>
          </div>
        </div>

        {/* Pagination */}
        {pagination.total > pagination.size && (
          <div className="mt-6">
        <PaginationControls
          current={pagination.page}
          size={pagination.size}
          total={pagination.total}
          onChange={changePage}
        />
          </div>
        )}
      </div>
    </div>
  );
}

function Header({ label }: { label: string }) {
  return (
    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
      {label}
    </th>
  );
}

function Cell({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <td className={`whitespace-nowrap px-6 py-4 text-sm ${className}`}>{children}</td>;
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
    <div className="bg-white rounded-lg border border-gray-200 px-6 py-4 flex items-center justify-between">
      <div className="text-sm text-gray-700">
        Showing <span className="font-medium">{(current - 1) * size + 1}</span> to{" "}
        <span className="font-medium">{Math.min(current * size, total)}</span> of{" "}
        <span className="font-medium">{total}</span> appointments
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="inline-flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          onClick={() => onChange(Math.max(1, current - 1))}
          disabled={current <= 1}
        >
          Previous
        </button>
        <span className="px-4 py-2 text-sm text-gray-700">
          Page {current} of {maxPage}
        </span>
        <button
          type="button"
          className="inline-flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-700" htmlFor={name}>
        {label}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        placeholder={placeholder}
        className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
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
