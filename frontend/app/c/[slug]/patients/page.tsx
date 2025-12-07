"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { z } from "zod";
import { Users, UserPlus, RefreshCw, Search, Edit, Trash2, X, CheckCircle2, XCircle, Eye, Calendar, Phone, Mail, MapPin, Heart, FileText, User, AlertTriangle, Copy, Check } from "lucide-react";

type Patient = {
  id: number;
  full_name: string;
  phone_number: string;
  alternative_phone: string;
  email: string;
  emergency_contact_name: string;
  emergency_contact_phone: string;
  date_of_birth: string | null;
  age: number | null;
  gender: string;
  city: string;
  district: string;
  address: string;
  allergies: string;
  chronic_diseases: string;
  current_medications: string;
  blood_type: string;
  notes: string;
  language: string;
  created_at: string;
};

const patientSchema = z.object({
  full_name: z.string().min(1),
  phone_number: z.string().min(1),
  alternative_phone: z.string().optional(),
  email: z.string().email().optional().or(z.literal("")),
  emergency_contact_name: z.string().optional(),
  emergency_contact_phone: z.string().optional(),
  date_of_birth: z.string().optional().or(z.literal("")),
  gender: z.enum(["male", "female", "other", ""]).optional(),
  city: z.string().optional(),
  district: z.string().optional(),
  address: z.string().optional(),
  allergies: z.string().optional(),
  chronic_diseases: z.string().optional(),
  current_medications: z.string().optional(),
  blood_type: z.string().optional(),
  notes: z.string().optional(),
  language: z.enum(["en", "ar", "en_US"]),
});

export default function PatientsPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const queryClient = useQueryClient();
  const { support } = useSupportSession();
  const readOnly = Boolean(support);

  const [search, setSearch] = useState<string>("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [viewingPatient, setViewingPatient] = useState<Patient | null>(null);
  const [editingPatient, setEditingPatient] = useState<Patient | null>(null);

  // Form states - Basic Info
  const [formName, setFormName] = useState("");
  const [formPhone, setFormPhone] = useState("");
  const [formAltPhone, setFormAltPhone] = useState("");
  const [formEmail, setFormEmail] = useState("");
  const [formLanguage, setFormLanguage] = useState<"en" | "ar" | "en_US">("ar");
  
  // Form states - Personal Info
  const [formDOB, setFormDOB] = useState("");
  const [formGender, setFormGender] = useState<"male" | "female" | "other" | "">("");
  
  // Form states - Emergency Contact
  const [formEmergencyName, setFormEmergencyName] = useState("");
  const [formEmergencyPhone, setFormEmergencyPhone] = useState("");
  
  // Form states - Address
  const [formCity, setFormCity] = useState("");
  const [formDistrict, setFormDistrict] = useState("");
  const [formAddress, setFormAddress] = useState("");
  
  // Form states - Medical Info
  const [formAllergies, setFormAllergies] = useState("");
  const [formChronicDiseases, setFormChronicDiseases] = useState("");
  const [formCurrentMedications, setFormCurrentMedications] = useState("");
  const [formBloodType, setFormBloodType] = useState("");
  
  // Form states - Notes
  const [formNotes, setFormNotes] = useState("");
  
  // Delete confirmation state
  const [deleteConfirmation, setDeleteConfirmation] = useState<{ id: number; name: string } | null>(null);
  
  // Copy ID state
  const [copiedId, setCopiedId] = useState(false);

  const patientsQuery = useQuery({
    queryKey: ["patients", slug, search],
    queryFn: async () => {
      const searchParam = search ? `?search=${encodeURIComponent(search)}` : "";
      const response = await fetch(`/api/proxy/clinic/${slug}/patients${searchParam}`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load patients");
      }
      return payload.data.items as Patient[];
    },
  });

  const createMutation = useMutation({
    mutationFn: async (payload: z.infer<typeof patientSchema>) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/patients`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "CREATE_FAILED");
      }
      return result.data as Patient;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["patients", slug] });
      setFeedback("Patient created successfully");
      setError(null);
      setShowModal(false);
      resetForm();
    },
    onError: (err: Error) => {
      setError(humanizeError(err.message));
      setFeedback(null);
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, payload }: { id: number; payload: z.infer<typeof patientSchema> }) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/patients/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "UPDATE_FAILED");
      }
      return result.data as Patient;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["patients", slug] });
      setFeedback("Patient updated successfully");
      setError(null);
      setEditingPatient(null);
      setShowModal(false);
      resetForm();
    },
    onError: (err: Error) => {
      setError(humanizeError(err.message));
      setFeedback(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/patients/${id}`, {
        method: "DELETE",
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "DELETE_FAILED");
      }
      return result;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["patients", slug] });
      setFeedback("Patient deleted successfully");
      setError(null);
      setViewingPatient(null);
    },
    onError: (err: Error) => {
      setError(humanizeError(err.message));
      setFeedback(null);
    },
  });

  const patients = useMemo(() => patientsQuery.data ?? [], [patientsQuery.data]);

  function resetForm() {
    setFormName("");
    setFormPhone("");
    setFormAltPhone("");
    setFormEmail("");
    setFormLanguage("ar");
    setFormDOB("");
    setFormGender("");
    setFormEmergencyName("");
    setFormEmergencyPhone("");
    setFormCity("");
    setFormDistrict("");
    setFormAddress("");
    setFormAllergies("");
    setFormChronicDiseases("");
    setFormCurrentMedications("");
    setFormBloodType("");
    setFormNotes("");
  }

  function loadPatientToForm(patient: Patient) {
    setFormName(patient.full_name);
    setFormPhone(patient.phone_number);
    setFormAltPhone(patient.alternative_phone || "");
    setFormEmail(patient.email || "");
    setFormLanguage(patient.language as "en" | "ar" | "en_US");
    setFormDOB(patient.date_of_birth || "");
    setFormGender((patient.gender as "male" | "female" | "other") || "");
    setFormEmergencyName(patient.emergency_contact_name || "");
    setFormEmergencyPhone(patient.emergency_contact_phone || "");
    setFormCity(patient.city || "");
    setFormDistrict(patient.district || "");
    setFormAddress(patient.address || "");
    setFormAllergies(patient.allergies || "");
    setFormChronicDiseases(patient.chronic_diseases || "");
    setFormCurrentMedications(patient.current_medications || "");
    setFormBloodType(patient.blood_type || "");
    setFormNotes(patient.notes || "");
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly) {
      setError("Cannot modify patients while impersonating");
      return;
    }

    const payload = {
      full_name: formName,
      phone_number: formPhone,
      alternative_phone: formAltPhone || undefined,
      email: formEmail || undefined,
      emergency_contact_name: formEmergencyName || undefined,
      emergency_contact_phone: formEmergencyPhone || undefined,
      date_of_birth: formDOB || undefined,
      gender: formGender || undefined,
      city: formCity || undefined,
      district: formDistrict || undefined,
      address: formAddress || undefined,
      allergies: formAllergies || undefined,
      chronic_diseases: formChronicDiseases || undefined,
      current_medications: formCurrentMedications || undefined,
      blood_type: formBloodType || undefined,
      notes: formNotes || undefined,
      language: formLanguage,
    };

    const parsed = patientSchema.safeParse(payload);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid form");
      return;
    }

    if (editingPatient) {
      updateMutation.mutate({ id: editingPatient.id, payload: parsed.data });
    } else {
      createMutation.mutate(parsed.data);
    }
  }

  function handleViewPatient(patient: Patient) {
    setViewingPatient(patient);
  }

  function handleEditPatient(patient: Patient) {
    setEditingPatient(patient);
    loadPatientToForm(patient);
    setShowModal(true);
  }

  function handleDeletePatient(id: number, name: string) {
    if (readOnly) return;
    setDeleteConfirmation({ id, name });
  }
  
  function confirmDelete() {
    if (deleteConfirmation) {
      deleteMutation.mutate(deleteConfirmation.id);
      setDeleteConfirmation(null);
    }
  }
  
  function cancelDelete() {
    setDeleteConfirmation(null);
  }
  
  function copyPatientId(id: number) {
    navigator.clipboard.writeText(id.toString());
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  }

  function humanizeError(code: string): string {
    const errors: Record<string, string> = {
      INVALID_PAYLOAD: "Missing required fields",
      INVALID_EMAIL: "Invalid email address",
      PHONE_EXISTS: "Phone number already exists",
      PATIENT_NOT_FOUND: "Patient not found",
      PATIENT_HAS_APPOINTMENTS: "Cannot delete patient with existing appointments",
      INVALID_DATE: "Invalid date format",
    };
    return errors[code] || code;
  }

  function formatDate(isoString: string): string {
    try {
      return new Date(isoString).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return isoString;
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 shadow-lg">
              <Users className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Patients</h1>
              <p className="text-sm text-gray-600 mt-0.5">Complete patient records management</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => patientsQuery.refetch()}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 transition-colors shadow-sm"
              disabled={patientsQuery.isRefetching}
            >
              <RefreshCw className={`w-4 h-4 ${patientsQuery.isRefetching ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
            {!readOnly && (
              <button
                type="button"
                onClick={() => {
                  resetForm();
                  setEditingPatient(null);
                  setShowModal(true);
                }}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 transition-all shadow-lg"
              >
                <UserPlus className="w-4 h-4" />
                <span>Add Patient</span>
              </button>
            )}
          </div>
        </div>

        {/* Feedback Messages */}
        {feedback && (
          <div className="flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-xl">
            <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
            <span className="text-sm font-medium text-green-800">{feedback}</span>
            <button
              type="button"
              className="ml-auto p-1 rounded-lg hover:bg-green-100 transition-colors"
              onClick={() => setFeedback(null)}
            >
              <X className="w-4 h-4 text-green-600" />
            </button>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-xl">
            <XCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
            <span className="text-sm font-medium text-red-800">{error}</span>
            <button
              type="button"
              className="ml-auto p-1 rounded-lg hover:bg-red-100 transition-colors"
              onClick={() => setError(null)}
            >
              <X className="w-4 h-4 text-red-600" />
            </button>
          </div>
        )}

        {/* Search Bar */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              placeholder="Search by name, phone, or email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-11 pr-4 py-3 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            />
          </div>
        </div>

        {/* Patients Table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          {patientsQuery.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <span className="ml-3 text-sm text-gray-600">Loading patients...</span>
            </div>
          ) : patients.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Users className="w-16 h-16 text-gray-400 mb-4" />
              <p className="text-lg font-medium text-gray-900 mb-1">No patients found</p>
              <p className="text-sm text-gray-500">
                {search ? "Try a different search term" : "Add your first patient to get started"}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
                  <tr>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      ID
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      Name
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      Phone
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      Age / Gender
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      City
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      Language
                    </th>
                    <th className="px-6 py-4 text-right text-xs font-semibold text-gray-700 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {patients.map((patient) => (
                    <tr key={patient.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="inline-flex items-center gap-2">
                          <span className="text-xs font-mono font-semibold text-blue-600 bg-blue-50 px-2.5 py-1 rounded-md">
                            #{patient.id}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-semibold text-gray-900">{patient.full_name}</div>
                        {patient.email && (
                          <div className="text-xs text-gray-500">{patient.email}</div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-600">{patient.phone_number}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-600">
                          {patient.age ? `${patient.age} years` : "—"}
                          {patient.gender && ` • ${patient.gender}`}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-600">{patient.city || "—"}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            patient.language === "ar"
                              ? "bg-amber-100 text-amber-700"
                              : patient.language === "en_US"
                              ? "bg-blue-100 text-blue-700"
                              : "bg-green-100 text-green-700"
                          }`}
                        >
                          {patient.language === "ar"
                            ? "Arabic"
                            : patient.language === "en_US"
                            ? "English (US)"
                            : "English"}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => handleViewPatient(patient)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-green-600 hover:bg-green-50 transition-colors"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            <span>View</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => handleEditPatient(patient)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-blue-600 hover:bg-blue-50 transition-colors"
                            disabled={readOnly}
                          >
                            <Edit className="w-3.5 h-3.5" />
                            <span>Edit</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeletePatient(patient.id, patient.full_name)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 hover:bg-red-50 transition-colors"
                            disabled={readOnly}
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span>Delete</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Add/Edit Modal */}
        {showModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col">
              <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between rounded-t-xl flex-shrink-0">
                <h2 className="text-xl font-semibold text-gray-900">
                  {editingPatient ? "Edit Patient" : "Add New Patient"}
                </h2>
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    setEditingPatient(null);
                    resetForm();
                  }}
                  className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  <X className="w-5 h-5 text-gray-600" />
                </button>
              </div>

              <form id="patient-form" onSubmit={handleSubmit} className="flex-1 overflow-y-auto">
                <div className="p-6 space-y-6">
                  {/* Basic Information */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                      <User className="w-5 h-5 text-blue-600" />
                      Basic Information
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Full Name <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="text"
                          value={formName}
                          onChange={(e) => setFormName(e.target.value)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          required
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Date of Birth
                        </label>
                        <input
                          type="date"
                          value={formDOB}
                          onChange={(e) => setFormDOB(e.target.value)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Gender
                        </label>
                        <select
                          value={formGender}
                          onChange={(e) => setFormGender(e.target.value as any)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        >
                          <option value="">Select</option>
                          <option value="male">Male</option>
                          <option value="female">Female</option>
                          <option value="other">Other</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Blood Type
                        </label>
                        <select
                          value={formBloodType}
                          onChange={(e) => setFormBloodType(e.target.value)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        >
                          <option value="">Select</option>
                          <option value="A+">A+</option>
                          <option value="A-">A-</option>
                          <option value="B+">B+</option>
                          <option value="B-">B-</option>
                          <option value="AB+">AB+</option>
                          <option value="AB-">AB-</option>
                          <option value="O+">O+</option>
                          <option value="O-">O-</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Language <span className="text-red-500">*</span>
                        </label>
                        <select
                          value={formLanguage}
                          onChange={(e) => setFormLanguage(e.target.value as any)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          required
                        >
                          <option value="ar">Arabic</option>
                          <option value="en">English</option>
                          <option value="en_US">English (US)</option>
                        </select>
                      </div>
                    </div>
                  </div>

                  {/* Contact Information */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                      <Phone className="w-5 h-5 text-green-600" />
                      Contact Information
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Primary Phone <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="tel"
                          value={formPhone}
                          onChange={(e) => setFormPhone(e.target.value)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          placeholder="+905356027135"
                          required
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Alternative Phone
                        </label>
                        <input
                          type="tel"
                          value={formAltPhone}
                          onChange={(e) => setFormAltPhone(e.target.value)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        />
                      </div>

                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Email
                        </label>
                        <input
                          type="email"
                          value={formEmail}
                          onChange={(e) => setFormEmail(e.target.value)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Emergency Contact */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                      <Phone className="w-5 h-5 text-red-600" />
                      Emergency Contact
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Contact Name
                        </label>
                        <input
                          type="text"
                          value={formEmergencyName}
                          onChange={(e) => setFormEmergencyName(e.target.value)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Contact Phone
                        </label>
                        <input
                          type="tel"
                          value={formEmergencyPhone}
                          onChange={(e) => setFormEmergencyPhone(e.target.value)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Address */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                      <MapPin className="w-5 h-5 text-purple-600" />
                      Address
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          City
                        </label>
                        <input
                          type="text"
                          value={formCity}
                          onChange={(e) => setFormCity(e.target.value)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          District
                        </label>
                        <input
                          type="text"
                          value={formDistrict}
                          onChange={(e) => setFormDistrict(e.target.value)}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        />
                      </div>

                      <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Full Address
                        </label>
                        <textarea
                          value={formAddress}
                          onChange={(e) => setFormAddress(e.target.value)}
                          rows={2}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Medical Information */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                      <Heart className="w-5 h-5 text-red-500" />
                      Medical Information
                    </h3>
                    <div className="space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Allergies
                        </label>
                        <textarea
                          value={formAllergies}
                          onChange={(e) => setFormAllergies(e.target.value)}
                          rows={2}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                          placeholder="List any known allergies..."
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Chronic Diseases
                        </label>
                        <textarea
                          value={formChronicDiseases}
                          onChange={(e) => setFormChronicDiseases(e.target.value)}
                          rows={2}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                          placeholder="List any chronic conditions..."
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Current Medications
                        </label>
                        <textarea
                          value={formCurrentMedications}
                          onChange={(e) => setFormCurrentMedications(e.target.value)}
                          rows={2}
                          className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                          placeholder="List current medications..."
                        />
                      </div>
                    </div>
                  </div>

                  {/* Notes */}
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                      <FileText className="w-5 h-5 text-gray-600" />
                      General Notes
                    </h3>
                    <textarea
                      value={formNotes}
                      onChange={(e) => setFormNotes(e.target.value)}
                      rows={3}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                      placeholder="Additional notes about the patient..."
                    />
                  </div>
                </div>
              </form>

              {/* Form Actions - Fixed at bottom */}
              <div className="bg-white border-t border-gray-200 px-6 py-4 rounded-b-xl flex items-center justify-end gap-3 flex-shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    setEditingPatient(null);
                    resetForm();
                  }}
                  className="px-4 py-2.5 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  form="patient-form"
                  className="px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 transition-all shadow-lg disabled:opacity-50"
                  disabled={createMutation.isPending || updateMutation.isPending}
                >
                  {createMutation.isPending || updateMutation.isPending ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white inline-block mr-2"></div>
                      {editingPatient ? "Updating..." : "Creating..."}
                    </>
                  ) : editingPatient ? (
                    "Update Patient"
                  ) : (
                    "Create Patient"
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* View Patient Modal - للمشاهدة فقط */}
        {viewingPatient && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col">
              <div className="bg-gradient-to-r from-blue-600 to-blue-700 px-6 py-4 flex items-center justify-between rounded-t-xl flex-shrink-0">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-full bg-white/20 flex items-center justify-center">
                    <User className="w-6 h-6 text-white" />
                  </div>
                  <div>
                    <h2 className="text-xl font-semibold text-white">{viewingPatient.full_name}</h2>
                    <p className="text-sm text-blue-100">Patient Details</p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setViewingPatient(null)}
                  className="p-2 rounded-lg hover:bg-white/10 transition-colors"
                >
                  <X className="w-5 h-5 text-white" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* Basic Information */}
                <div className="bg-gray-50 rounded-lg p-4">
                  <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">Basic Information</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="col-span-2">
                      <p className="text-xs text-gray-500 mb-1.5">Patient ID</p>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-mono font-bold text-blue-600 bg-blue-50 px-3 py-1.5 rounded-md">
                          #{viewingPatient.id}
                        </span>
                        <button
                          type="button"
                          onClick={() => copyPatientId(viewingPatient.id)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-gray-600 hover:bg-gray-200 transition-colors"
                          title="Copy Patient ID"
                        >
                          {copiedId ? (
                            <>
                              <Check className="w-3.5 h-3.5 text-green-600" />
                              <span className="text-green-600">Copied!</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3.5 h-3.5" />
                              <span>Copy ID</span>
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Date of Birth</p>
                      <p className="text-sm font-medium text-gray-900">
                        {viewingPatient.date_of_birth ? formatDate(viewingPatient.date_of_birth) : "—"}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Age</p>
                      <p className="text-sm font-medium text-gray-900">
                        {viewingPatient.age ? `${viewingPatient.age} years` : "—"}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Gender</p>
                      <p className="text-sm font-medium text-gray-900 capitalize">
                        {viewingPatient.gender || "—"}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-500">Blood Type</p>
                      <p className="text-sm font-medium text-gray-900">
                        {viewingPatient.blood_type || "—"}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Contact Information */}
                <div className="bg-gray-50 rounded-lg p-4">
                  <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">Contact</h3>
                  <div className="space-y-3">
                    <div>
                      <p className="text-xs text-gray-500">Primary Phone</p>
                      <p className="text-sm font-medium text-gray-900">{viewingPatient.phone_number}</p>
                    </div>
                    {viewingPatient.alternative_phone && (
                      <div>
                        <p className="text-xs text-gray-500">Alternative Phone</p>
                        <p className="text-sm font-medium text-gray-900">{viewingPatient.alternative_phone}</p>
                      </div>
                    )}
                    {viewingPatient.email && (
                      <div>
                        <p className="text-xs text-gray-500">Email</p>
                        <p className="text-sm font-medium text-gray-900">{viewingPatient.email}</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Emergency Contact */}
                {(viewingPatient.emergency_contact_name || viewingPatient.emergency_contact_phone) && (
                  <div className="bg-red-50 rounded-lg p-4">
                    <h3 className="text-sm font-semibold text-red-700 uppercase tracking-wider mb-3">Emergency Contact</h3>
                    <div className="space-y-2">
                      {viewingPatient.emergency_contact_name && (
                        <div>
                          <p className="text-xs text-red-600">Name</p>
                          <p className="text-sm font-medium text-gray-900">{viewingPatient.emergency_contact_name}</p>
                        </div>
                      )}
                      {viewingPatient.emergency_contact_phone && (
                        <div>
                          <p className="text-xs text-red-600">Phone</p>
                          <p className="text-sm font-medium text-gray-900">{viewingPatient.emergency_contact_phone}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Address */}
                {(viewingPatient.city || viewingPatient.district || viewingPatient.address) && (
                  <div className="bg-gray-50 rounded-lg p-4">
                    <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">Address</h3>
                    <div className="space-y-2">
                      {viewingPatient.city && (
                        <p className="text-sm text-gray-900"><span className="font-medium">City:</span> {viewingPatient.city}</p>
                      )}
                      {viewingPatient.district && (
                        <p className="text-sm text-gray-900"><span className="font-medium">District:</span> {viewingPatient.district}</p>
                      )}
                      {viewingPatient.address && (
                        <p className="text-sm text-gray-900">{viewingPatient.address}</p>
                      )}
                    </div>
                  </div>
                )}

                {/* Medical Information */}
                {(viewingPatient.allergies || viewingPatient.chronic_diseases || viewingPatient.current_medications) && (
                  <div className="bg-red-50 rounded-lg p-4">
                    <h3 className="text-sm font-semibold text-red-700 uppercase tracking-wider mb-3">Medical Information</h3>
                    <div className="space-y-3">
                      {viewingPatient.allergies && (
                        <div>
                          <p className="text-xs text-red-600 font-medium">Allergies</p>
                          <p className="text-sm text-gray-900 whitespace-pre-wrap">{viewingPatient.allergies}</p>
                        </div>
                      )}
                      {viewingPatient.chronic_diseases && (
                        <div>
                          <p className="text-xs text-red-600 font-medium">Chronic Diseases</p>
                          <p className="text-sm text-gray-900 whitespace-pre-wrap">{viewingPatient.chronic_diseases}</p>
                        </div>
                      )}
                      {viewingPatient.current_medications && (
                        <div>
                          <p className="text-xs text-red-600 font-medium">Current Medications</p>
                          <p className="text-sm text-gray-900 whitespace-pre-wrap">{viewingPatient.current_medications}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Notes */}
                {viewingPatient.notes && (
                  <div className="bg-yellow-50 rounded-lg p-4">
                    <h3 className="text-sm font-semibold text-yellow-700 uppercase tracking-wider mb-2">Notes</h3>
                    <p className="text-sm text-gray-900 whitespace-pre-wrap">{viewingPatient.notes}</p>
                  </div>
                )}
              </div>

              {/* Actions - Fixed at bottom */}
              <div className="bg-white border-t border-gray-200 px-6 py-4 rounded-b-xl flex items-center justify-end gap-3 flex-shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    setViewingPatient(null);
                    handleEditPatient(viewingPatient);
                  }}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 transition-colors shadow-sm"
                  disabled={readOnly}
                >
                  <Edit className="w-4 h-4" />
                  Edit Patient
                </button>
                <button
                  type="button"
                  onClick={() => setViewingPatient(null)}
                  className="px-4 py-2.5 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {deleteConfirmation && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full overflow-hidden">
              {/* Header */}
              <div className="bg-gradient-to-r from-red-500 to-red-600 px-6 py-4 flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-white/20 flex items-center justify-center">
                  <AlertTriangle className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h2 className="text-xl font-semibold text-white">Confirm Delete</h2>
                  <p className="text-sm text-red-100">This action cannot be undone</p>
                </div>
              </div>

              {/* Body */}
              <div className="p-6">
                <p className="text-gray-700 text-base leading-relaxed">
                  Are you sure you want to delete patient <span className="font-semibold text-gray-900">"{deleteConfirmation.name}"</span>?
                </p>
                <p className="text-sm text-gray-500 mt-2">
                  All patient data will be permanently removed from the system.
                </p>
              </div>

              {/* Footer */}
              <div className="bg-gray-50 px-6 py-4 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={cancelDelete}
                  className="px-4 py-2.5 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 transition-colors"
                  disabled={deleteMutation.isPending}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={confirmDelete}
                  className="px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 transition-all shadow-lg disabled:opacity-50 inline-flex items-center gap-2"
                  disabled={deleteMutation.isPending}
                >
                  {deleteMutation.isPending ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Deleting...
                    </>
                  ) : (
                    <>
                      <Trash2 className="w-4 h-4" />
                      Delete Patient
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
