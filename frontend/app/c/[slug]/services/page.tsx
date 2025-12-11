"use client";

import { useEffect, useMemo, useState } from "react";
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

  const [serviceRows, setServiceRows] = useState<Service[]>([]);
  const [hoursRows, setHoursRows] = useState<ServiceHours[]>([]);
  const [existingServiceCodes, setExistingServiceCodes] = useState<Set<string>>(new Set());
  const [originalServices, setOriginalServices] = useState<Service[]>([]);
  const [serviceChanges, setServiceChanges] = useState<Map<number, boolean>>(new Map());
  const [deleteConfirm, setDeleteConfirm] = useState<{ index: number; service: Service | null } | null>(null);
  const [originalHours, setOriginalHours] = useState<ServiceHours[]>([]);
  const [hoursChanges, setHoursChanges] = useState<Map<number, boolean>>(new Map());
  const [deleteHourConfirm, setDeleteHourConfirm] = useState<{ index: number; hour: ServiceHours | null } | null>(null);
  const [existingHoursKeys, setExistingHoursKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    // Track existing service codes
    const codes = new Set(services.map(s => s.code));
    setExistingServiceCodes(codes);
    setOriginalServices(services);
    
    // Start with one empty service if no services exist, otherwise show existing ones
    if (services.length === 0) {
      setServiceRows([
        {
          code: "",
          name: "",
          description: "",
          duration_minutes: 30,
          language: "ar",
          is_active: true,
        },
      ]);
    } else {
      setServiceRows(services);
    }
    // Reset changes tracking
    setServiceChanges(new Map());
  }, [services]);

  useEffect(() => {
    setHoursRows(hours);
    setOriginalHours(hours);
    // Create a set of unique keys for existing hours
    const keys = new Set(
      hours.map(h => `${h.service_code}-${h.weekday}-${h.start_time}-${h.end_time}`)
    );
    setExistingHoursKeys(keys);
    // Reset changes tracking
    setHoursChanges(new Map());
  }, [hours]);

  function checkServiceChanges(index: number, formData: FormData): boolean {
    const original = originalServices[index];
    if (!original) return false;

    const current = {
      code: String(formData.get(`service_code_${index}`) || "").trim(),
      name: String(formData.get(`service_name_${index}`) || "").trim(),
      description: String(formData.get(`service_desc_${index}`) || "").trim(),
      duration_minutes: Number(formData.get(`service_duration_${index}`) || 0),
      language: String(formData.get(`service_lang_${index}`) || "").trim(),
      is_active: formData.get(`service_active_${index}`) === "on",
    };

    return (
      current.code !== original.code ||
      current.name !== original.name ||
      current.description !== (original.description || "") ||
      current.duration_minutes !== original.duration_minutes ||
      current.language !== original.language ||
      current.is_active !== original.is_active
    );
  }

  function handleServiceFieldChange(index: number, isExistingService: boolean) {
    if (!isExistingService) return;
    setTimeout(() => {
      const form = document.querySelector(`form[data-service-form]`) as HTMLFormElement;
      if (!form) return;
      
      const formData = new FormData(form);
      const hasChanges = checkServiceChanges(index, formData);
      setServiceChanges(prev => {
        const next = new Map(prev);
        next.set(index, hasChanges);
        return next;
      });
    }, 0);
  }

  function handleUpdateService(index: number) {
    const form = document.querySelector(`form[data-service-form]`) as HTMLFormElement;
    if (!form) return;
    
    const formData = new FormData(form);
    
    // Get all services, updating the one at index
    const allServices = serviceRows.map((s, i) => {
      if (i === index) {
        return {
          code: String(formData.get(`service_code_${index}`) || "").trim(),
          name: String(formData.get(`service_name_${index}`) || "").trim(),
          description: String(formData.get(`service_desc_${index}`) || "").trim(),
          duration_minutes: Number(formData.get(`service_duration_${index}`) || 0),
          language: String(formData.get(`service_lang_${index}`) || "").trim(),
          is_active: formData.get(`service_active_${index}`) === "on",
        };
      }
      return s;
    });

    const payload = {
      services: allServices,
    };

    const parsed = serviceSchema.safeParse(payload);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid service data");
      setFeedback(null);
      return;
    }

    // Update the service in the list
    setServiceRows(allServices as Service[]);

    // Update original services
    setOriginalServices(allServices.filter((s, i) => 
      existingServiceCodes.has(s.code) && i < originalServices.length
    ) as Service[]);

    // Clear changes for this service
    setServiceChanges(prev => {
      const next = new Map(prev);
      next.delete(index);
      return next;
    });

    // Submit update
    updateServices.mutate(parsed.data);
  }

  function handleCancelServiceChanges(index: number) {
    const original = originalServices[index];
    if (!original) return;

    // Reset service to original values
    setServiceRows(prev => {
      const next = [...prev];
      next[index] = original;
      return next;
    });

    // Clear changes
    setServiceChanges(prev => {
      const next = new Map(prev);
      next.delete(index);
      return next;
    });

    // Force form reset by triggering a re-render
    setTimeout(() => {
      const form = document.querySelector(`form[data-service-form]`) as HTMLFormElement;
      if (form) {
        const codeInput = form.querySelector(`input[name="service_code_${index}"]`) as HTMLInputElement;
        const nameInput = form.querySelector(`input[name="service_name_${index}"]`) as HTMLInputElement;
        const durationInput = form.querySelector(`input[name="service_duration_${index}"]`) as HTMLInputElement;
        const langSelect = form.querySelector(`select[name="service_lang_${index}"]`) as HTMLSelectElement;
        const activeCheckbox = form.querySelector(`input[name="service_active_${index}"]`) as HTMLInputElement;
        const descTextarea = form.querySelector(`textarea[name="service_desc_${index}"]`) as HTMLTextAreaElement;
        
        if (codeInput) codeInput.value = original.code;
        if (nameInput) nameInput.value = original.name;
        if (durationInput) durationInput.value = String(original.duration_minutes);
        if (langSelect) langSelect.value = original.language;
        if (activeCheckbox) activeCheckbox.checked = original.is_active;
        if (descTextarea) descTextarea.value = original.description || "";
      }
    }, 0);
  }

  function handleDeleteService(index: number, service: Service) {
    const isExisting = service.code && existingServiceCodes.has(service.code);
    if (isExisting) {
      // Show confirmation dialog for existing services
      setDeleteConfirm({ index, service });
    } else {
      // Delete new service immediately (no confirmation needed)
      setServiceRows((prev) => prev.filter((_, i) => i !== index));
    }
  }

  function confirmDeleteService() {
    if (!deleteConfirm) return;
    
    const { index, service } = deleteConfirm;
    const isExisting = service?.code && existingServiceCodes.has(service.code);
    
    // Remove from UI immediately
    setServiceRows((prev) => prev.filter((_, i) => i !== index));
    
    // If it was an existing service, we need to save the updated list to backend
    if (isExisting) {
      // Get remaining services (excluding the deleted one)
      const remainingServices = serviceRows
        .filter((_, i) => i !== index)
        .map((s) => ({
          code: s.code || "",
          name: s.name || "",
          description: s.description || "",
          duration_minutes: s.duration_minutes || 0,
          language: s.language || "",
          is_active: s.is_active ?? true,
        }));

      const payload = {
        services: remainingServices,
      };

      const parsed = serviceSchema.safeParse(payload);
      if (parsed.success) {
        updateServices.mutate(parsed.data);
      }
    }
    
    setDeleteConfirm(null);
  }

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
        code:
          String(formData.get(`service_code_${index}`) || "").trim() ||
          (serviceRows[index]?.code ?? ""),
        name:
          String(formData.get(`service_name_${index}`) || "").trim() ||
          (serviceRows[index]?.name ?? ""),
        description:
          String(formData.get(`service_desc_${index}`) || "").trim() ||
          (serviceRows[index]?.description ?? ""),
        duration_minutes:
          Number(formData.get(`service_duration_${index}`) || 0) ||
          Number(serviceRows[index]?.duration_minutes ?? 0),
        language:
          String(formData.get(`service_lang_${index}`) || "").trim() ||
          (serviceRows[index]?.language ?? ""),
        is_active:
          formData.has(`service_active_${index}`)
            ? formData.get(`service_active_${index}`) === "on"
            : Boolean(serviceRows[index]?.is_active ?? true),
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

  function checkHourChanges(index: number, formData: FormData, currentHour: ServiceHours): boolean {
    const currentKey = `${currentHour.service_code}-${currentHour.weekday}-${currentHour.start_time}-${currentHour.end_time}`;
    const original = originalHours.find(oh => 
      `${oh.service_code}-${oh.weekday}-${oh.start_time}-${oh.end_time}` === currentKey
    );
    if (!original) return false;

    const current = {
      service_code: String(formData.get(`hour_service_${index}`) || "").trim(),
      weekday: Number(formData.get(`hour_weekday_${index}`) || 0),
      start_time: String(formData.get(`hour_start_${index}`) || "").trim(),
      end_time: String(formData.get(`hour_end_${index}`) || "").trim(),
    };

    return (
      current.service_code !== original.service_code ||
      current.weekday !== original.weekday ||
      current.start_time !== original.start_time ||
      current.end_time !== original.end_time
    );
  }

  function handleHourFieldChange(index: number, isExisting: boolean) {
    if (!isExisting) return;
    setTimeout(() => {
      const form = document.querySelector(`form[data-hours-form]`) as HTMLFormElement;
      if (!form) return;
      
      const formData = new FormData(form);
      const currentHour = hoursRows[index];
      if (!currentHour) return;
      
      const hasChanges = checkHourChanges(index, formData, currentHour);
      setHoursChanges(prev => {
        const next = new Map(prev);
        next.set(index, hasChanges);
        return next;
      });
    }, 0);
  }

  function handleUpdateHour(index: number) {
    const form = document.querySelector(`form[data-hours-form]`) as HTMLFormElement;
    if (!form) return;
    
    const formData = new FormData(form);
    
    // Get all hours, updating the one at index
    const allHours = hoursRows.map((h, i) => {
      if (i === index) {
        return {
          service_code: String(formData.get(`hour_service_${index}`) || "").trim(),
          weekday: Number(formData.get(`hour_weekday_${index}`) || 0),
          start_time: String(formData.get(`hour_start_${index}`) || "").trim(),
          end_time: String(formData.get(`hour_end_${index}`) || "").trim(),
        };
      }
      return h;
    });

    const payload = {
      hours: allHours,
    };

    const parsed = hoursSchema.safeParse(payload);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid hours data");
      setFeedback(null);
      return;
    }

    // Update the hour in the list
    setHoursRows(allHours as ServiceHours[]);

    // Update original hours - replace the updated one
    const oldHour = hoursRows[index];
    const newHour = allHours[index] as ServiceHours;
    const oldKey = oldHour ? `${oldHour.service_code}-${oldHour.weekday}-${oldHour.start_time}-${oldHour.end_time}` : "";
    const newKey = `${newHour.service_code}-${newHour.weekday}-${newHour.start_time}-${newHour.end_time}`;
    
    // Update existing hours keys
    setExistingHoursKeys(prev => {
      const next = new Set(prev);
      if (oldKey && next.has(oldKey)) {
        next.delete(oldKey);
      }
      next.add(newKey);
      return next;
    });

    setOriginalHours(prev => {
      const next = [...prev];
      if (index < next.length) {
        next[index] = newHour;
      }
      return next;
    });

    // Clear changes for this hour
    setHoursChanges(prev => {
      const next = new Map(prev);
      next.delete(index);
      return next;
    });

    // Submit update
    updateHours.mutate(parsed.data);
  }

  function handleCancelHourChanges(index: number) {
    const currentHour = hoursRows[index];
    if (!currentHour) return;
    
    const currentKey = `${currentHour.service_code}-${currentHour.weekday}-${currentHour.start_time}-${currentHour.end_time}`;
    const original = originalHours.find(oh => 
      `${oh.service_code}-${oh.weekday}-${oh.start_time}-${oh.end_time}` === currentKey
    );
    if (!original) return;

    // Reset hour to original values
    setHoursRows(prev => {
      const next = [...prev];
      next[index] = original;
      return next;
    });

    // Clear changes
    setHoursChanges(prev => {
      const next = new Map(prev);
      next.delete(index);
      return next;
    });

    // Force form reset
    setTimeout(() => {
      const form = document.querySelector(`form[data-hours-form]`) as HTMLFormElement;
      if (form) {
        const serviceInput = form.querySelector(`input[name="hour_service_${index}"]`) as HTMLInputElement;
        const weekdayInput = form.querySelector(`input[name="hour_weekday_${index}"]`) as HTMLInputElement;
        const startInput = form.querySelector(`input[name="hour_start_${index}"]`) as HTMLInputElement;
        const endInput = form.querySelector(`input[name="hour_end_${index}"]`) as HTMLInputElement;
        
        if (serviceInput) serviceInput.value = original.service_code;
        if (weekdayInput) weekdayInput.value = String(original.weekday);
        if (startInput) startInput.value = original.start_time;
        if (endInput) endInput.value = original.end_time;
      }
    }, 0);
  }

  function handleDeleteHour(index: number, hour: ServiceHours) {
    // Check if this hour exists in original hours
    const hourKey = `${hour.service_code}-${hour.weekday}-${hour.start_time}-${hour.end_time}`;
    const isExisting = existingHoursKeys.has(hourKey);
    
    if (isExisting) {
      // Show confirmation dialog for existing hours
      setDeleteHourConfirm({ index, hour });
    } else {
      // Delete new hour immediately (no confirmation needed)
      setHoursRows((prev) => prev.filter((_, i) => i !== index));
    }
  }

  function confirmDeleteHour() {
    if (!deleteHourConfirm) return;
    
    const { index, hour } = deleteHourConfirm;
    const hourKey = hour ? `${hour.service_code}-${hour.weekday}-${hour.start_time}-${hour.end_time}` : "";
    const isExisting = hourKey && existingHoursKeys.has(hourKey);
    
    // Remove from UI immediately
    setHoursRows((prev) => prev.filter((_, i) => i !== index));
    
    // If it was an existing hour, we need to save the updated list to backend
    if (isExisting && hourKey) {
      // Remove from existing keys
      setExistingHoursKeys(prev => {
        const next = new Set(prev);
        next.delete(hourKey);
        return next;
      });
      
      // Get remaining hours (excluding the deleted one)
      const remainingHours = hoursRows
        .filter((_, i) => i !== index)
        .map((h) => ({
          service_code: h.service_code || "",
          weekday: h.weekday || 0,
          start_time: h.start_time || "",
          end_time: h.end_time || "",
        }));

      const payload = {
        hours: remainingHours,
      };

      const parsed = hoursSchema.safeParse(payload);
      if (parsed.success) {
        updateHours.mutate(parsed.data);
      }
    }
    
    setDeleteHourConfirm(null);
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
        service_code:
          String(formData.get(`hour_service_${index}`) || "").trim() ||
          (hoursRows[index]?.service_code ?? ""),
        weekday:
          Number(formData.get(`hour_weekday_${index}`) || 0) ||
          Number(hoursRows[index]?.weekday ?? 0),
        start_time:
          String(formData.get(`hour_start_${index}`) || "").trim() ||
          (hoursRows[index]?.start_time ?? ""),
        end_time:
          String(formData.get(`hour_end_${index}`) || "").trim() ||
          (hoursRows[index]?.end_time ?? ""),
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

        {/* Combined Services & Hours Section */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 space-y-8">
          {/* Services Section */}
          <div>
            {/* Services Info Card */}
            <div className="mb-6 rounded-lg bg-gradient-to-r from-indigo-50 to-purple-50 border border-indigo-200 p-4">
              <div className="flex items-start gap-3">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-indigo-100 flex-shrink-0">
                  <Settings className="w-5 h-5 text-indigo-600" />
                </div>
                <div className="flex-1">
                  <h2 className="text-lg font-semibold text-gray-900 mb-1">Services</h2>
                  <p className="text-sm text-gray-600">
                    Define your clinic's services with codes, names, durations, and languages. These services will appear in appointment booking and be used by the WhatsApp bot to answer patient inquiries.
                  </p>
                  <p className="text-xs text-gray-500 mt-2">
                    <span className="font-medium">Allowed languages:</span> ar, en only
                  </p>
                </div>
              </div>
            </div>

            <form className="space-y-4" onSubmit={handleServicesSubmit} data-service-form>
          <div className="flex justify-between items-center mb-2">
            <input type="hidden" name="rows" value={serviceRows.length} />
            <p className="text-xs text-gray-500">Allowed languages: ar, en only</p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() =>
                  setServiceRows((prev) => [
                    {
                      code: "",
                      name: "",
                      description: "",
                      duration_minutes: 30,
                      language: "ar",
                      is_active: true,
                    },
                    ...prev,
                  ])
                }
                disabled={readOnly}
                className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50"
              >
                <Plus className="w-4 h-4" />
                Add service
              </button>
            </div>
          </div>
          {serviceRows.map((service, index) => {
            const isExisting = service.code && existingServiceCodes.has(service.code);
            const hasChanges = serviceChanges.get(index) || false;
            return (
              <div 
                key={`${service.code || 'new'}-${index}`} 
                className={`rounded-lg border px-5 py-4 ${
                  isExisting 
                    ? 'border-blue-200 bg-blue-50' 
                    : 'border-gray-200 bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    {isExisting && (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700 border border-blue-200">
                        Existing Service
                      </span>
                    )}
                    {!isExisting && (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700 border border-green-200">
                        New Service
                      </span>
                    )}
                    {hasChanges && (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 border border-amber-200">
                        Modified
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {isExisting && hasChanges && (
                      <>
                        <button
                          type="button"
                          onClick={() => handleUpdateService(index)}
                          disabled={readOnly || updateServices.isPending}
                          className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                        >
                          <Save className="w-3 h-3" />
                          Update
                        </button>
                        <button
                          type="button"
                          onClick={() => handleCancelServiceChanges(index)}
                          disabled={readOnly}
                          className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50 transition-colors"
                        >
                          <X className="w-3 h-3" />
                          Cancel
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => handleDeleteService(index, service)}
                      className="text-xs text-red-600 hover:text-red-800 font-medium"
                      disabled={readOnly}
                    >
                      Delete
                    </button>
                  </div>
                </div>
                <div className="grid gap-4 md:grid-cols-3">
                <Field label="Code">
                  <input
                    name={`service_code_${index}`}
                    defaultValue={isExisting ? service.code : ""}
                    placeholder="consult_ar"
                    onChange={() => handleServiceFieldChange(index, !!isExisting)}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    required
                  />
                </Field>
                <Field label="Name">
                  <input
                    name={`service_name_${index}`}
                    defaultValue={isExisting ? service.name : ""}
                    placeholder="Comprehensive consultation"
                    onChange={() => handleServiceFieldChange(index, !!isExisting)}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    required
                  />
                </Field>
                <Field label="Duration (minutes)">
                  <input
                    name={`service_duration_${index}`}
                    type="number"
                    defaultValue={isExisting ? service.duration_minutes : ""}
                    placeholder="30"
                    onChange={() => handleServiceFieldChange(index, !!isExisting)}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    required
                  />
                </Field>
                <Field label="Language">
                  <select
                    name={`service_lang_${index}`}
                    defaultValue={isExisting ? service.language : ""}
                    onChange={() => handleServiceFieldChange(index, !!isExisting)}
                    className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    required
                  >
                    <option value="" disabled className="text-gray-400">
                      Select language
                    </option>
                    <option value="ar">Arabic (ar)</option>
                    <option value="en">English (en)</option>
                  </select>
                </Field>
                <Field label="Active">
                    <div className="flex items-center">
                  <input
                    name={`service_active_${index}`}
                    type="checkbox"
                    defaultChecked={service.is_active}
                    onChange={() => handleServiceFieldChange(index, !!isExisting)}
                        className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                    </div>
                </Field>
                <Field label="Description" className="md:col-span-3">
                  <textarea
                    name={`service_desc_${index}`}
                    defaultValue={isExisting ? service.description : ""}
                    placeholder="Dental checkup (30 min)"
                    onChange={() => handleServiceFieldChange(index, !!isExisting)}
                      rows={2}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                  />
                </Field>
              </div>
              </div>
            );
          })}
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
          <div className="border-t border-gray-200 pt-8">
            {/* Service Hours Info Card */}
            <div className="mb-6 rounded-lg bg-gradient-to-r from-purple-50 to-pink-50 border border-purple-200 p-4">
              <div className="flex items-start gap-3">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-purple-100 flex-shrink-0">
                  <Clock className="w-5 h-5 text-purple-600" />
                </div>
                <div className="flex-1">
                  <h2 className="text-lg font-semibold text-gray-900 mb-1">Service Hours</h2>
                  <p className="text-sm text-gray-600">
                    Set working hours for each service by day of the week. The system will validate appointment times against these hours and suggest available slots to patients via WhatsApp.
                  </p>
                  <p className="text-xs text-gray-500 mt-2">
                    <span className="font-medium">Weekday format:</span> 0 = Monday, 1 = Tuesday, ..., 6 = Sunday
                  </p>
                </div>
              </div>
            </div>

            <form className="space-y-4" onSubmit={handleHoursSubmit} data-hours-form>
          <div className="flex justify-between items-center mb-2">
            <input type="hidden" name="rows_hours" value={hoursRows.length} />
            <p className="text-xs text-gray-500">Add working windows per service (0 = Monday)</p>
            <button
              type="button"
              onClick={() =>
                setHoursRows((prev) => [
                  {
                    service_code: serviceRows[0]?.code || "",
                    weekday: 0,
                    start_time: "09:00",
                    end_time: "17:00",
                  },
                  ...prev,
                ])
              }
              disabled={readOnly}
              className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50"
            >
              <Plus className="w-4 h-4" />
              Add working window
            </button>
          </div>
          {hoursRows.map((hour, index) => {
            const hourKey = `${hour.service_code}-${hour.weekday}-${hour.start_time}-${hour.end_time}`;
            const isExisting = existingHoursKeys.has(hourKey);
            const hasChanges = hoursChanges.get(index) || false;
            return (
              <div 
                key={`${hour.service_code}-${hour.weekday}-${index}`} 
                className={`rounded-lg border px-5 py-4 ${
                  isExisting 
                    ? 'border-blue-200 bg-blue-50' 
                    : 'border-gray-200 bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    {isExisting && (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-700 border border-blue-200">
                        Existing Hours
                      </span>
                    )}
                    {!isExisting && (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700 border border-green-200">
                        New Hours
                      </span>
                    )}
                    {hasChanges && (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 border border-amber-200">
                        Modified
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {isExisting && hasChanges && (
                      <>
                        <button
                          type="button"
                          onClick={() => handleUpdateHour(index)}
                          disabled={readOnly || updateHours.isPending}
                          className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                        >
                          <Save className="w-3 h-3" />
                          Update
                        </button>
                        <button
                          type="button"
                          onClick={() => handleCancelHourChanges(index)}
                          disabled={readOnly}
                          className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50 transition-colors"
                        >
                          <X className="w-3 h-3" />
                          Cancel
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() => handleDeleteHour(index, hour)}
                      className="text-xs text-red-600 hover:text-red-800 font-medium"
                      disabled={readOnly}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              <div className="grid gap-4 md:grid-cols-4">
                  <Field label="Service Code">
                  <input
                    name={`hour_service_${index}`}
                    defaultValue={isExisting ? hour.service_code : ""}
                    placeholder="consult_ar"
                    onChange={() => handleHourFieldChange(index, isExisting)}
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
                    defaultValue={isExisting ? hour.weekday : ""}
                    placeholder="0 (Monday)"
                    onChange={() => handleHourFieldChange(index, isExisting)}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    required
                  />
                </Field>
                  <Field label="Start Time (HH:MM)">
                    <input
                      name={`hour_start_${index}`}
                      type="time"
                    defaultValue={isExisting ? hour.start_time : ""}
                    placeholder="09:00"
                    onChange={() => handleHourFieldChange(index, isExisting)}
                        className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      required
                    />
                  </Field>
                  <Field label="End Time (HH:MM)">
                    <input
                      name={`hour_end_${index}`}
                      type="time"
                    defaultValue={isExisting ? hour.end_time : ""}
                    placeholder="17:00"
                    onChange={() => handleHourFieldChange(index, isExisting)}
                        className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                      required
                    />
                  </Field>
              </div>
              </div>
            );
          })}
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

        {/* Delete Confirmation Dialog */}
        {deleteConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full">
              <div className="p-6">
                <div className="flex items-center gap-4 mb-4">
                  <div className="flex items-center justify-center w-12 h-12 rounded-full bg-red-100">
                    <AlertCircle className="w-6 h-6 text-red-600" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-gray-900">Delete Service</h3>
                    <p className="text-sm text-gray-600 mt-1">
                      Are you sure you want to delete this service?
                    </p>
                  </div>
                </div>
                {deleteConfirm.service && (
                  <div className="bg-gray-50 rounded-lg p-4 mb-4">
                    <p className="text-sm font-medium text-gray-900 mb-1">Service Details:</p>
                    <p className="text-sm text-gray-600">
                      <span className="font-medium">Code:</span> {deleteConfirm.service.code}
                    </p>
                    <p className="text-sm text-gray-600">
                      <span className="font-medium">Name:</span> {deleteConfirm.service.name}
                    </p>
                  </div>
                )}
                <p className="text-sm text-red-600 mb-4">
                  This action cannot be undone. The service will be permanently removed.
                </p>
                <div className="flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setDeleteConfirm(null)}
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={confirmDeleteService}
                    disabled={readOnly || updateServices.isPending}
                    className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
                  >
                    {updateServices.isPending ? "Deleting..." : "Delete Service"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Delete Hour Confirmation Dialog */}
        {deleteHourConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full">
              <div className="p-6">
                <div className="flex items-center gap-4 mb-4">
                  <div className="flex items-center justify-center w-12 h-12 rounded-full bg-red-100">
                    <AlertCircle className="w-6 h-6 text-red-600" />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-gray-900">Delete Working Hours</h3>
                    <p className="text-sm text-gray-600 mt-1">
                      Are you sure you want to delete this working hours entry?
                    </p>
                  </div>
                </div>
                {deleteHourConfirm.hour && (
                  <div className="bg-gray-50 rounded-lg p-4 mb-4">
                    <p className="text-sm font-medium text-gray-900 mb-1">Working Hours Details:</p>
                    <p className="text-sm text-gray-600">
                      <span className="font-medium">Service Code:</span> {deleteHourConfirm.hour.service_code}
                    </p>
                    <p className="text-sm text-gray-600">
                      <span className="font-medium">Weekday:</span> {deleteHourConfirm.hour.weekday === 0 ? "Monday" : 
                        deleteHourConfirm.hour.weekday === 1 ? "Tuesday" :
                        deleteHourConfirm.hour.weekday === 2 ? "Wednesday" :
                        deleteHourConfirm.hour.weekday === 3 ? "Thursday" :
                        deleteHourConfirm.hour.weekday === 4 ? "Friday" :
                        deleteHourConfirm.hour.weekday === 5 ? "Saturday" : "Sunday"} ({deleteHourConfirm.hour.weekday})
                    </p>
                    <p className="text-sm text-gray-600">
                      <span className="font-medium">Time:</span> {deleteHourConfirm.hour.start_time} - {deleteHourConfirm.hour.end_time}
                    </p>
                  </div>
                )}
                <p className="text-sm text-red-600 mb-4">
                  This action cannot be undone. The working hours entry will be permanently removed.
                </p>
                <div className="flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setDeleteHourConfirm(null)}
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={confirmDeleteHour}
                    disabled={readOnly || updateHours.isPending}
                    className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
                  >
                    {updateHours.isPending ? "Deleting..." : "Delete Hours"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
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
