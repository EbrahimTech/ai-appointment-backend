"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { Settings, Save, AlertCircle, CheckCircle2, Globe, Phone, MapPin, Clock, Languages } from "lucide-react";

type ClinicInfo = {
  name: string;
  slug: string;
  phone_number: string;
  whatsapp_number: string;
  address: string;
  tz: string;
  default_lang: string;
};

export default function ClinicSettingsPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const { support } = useSupportSession();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState<Partial<ClinicInfo>>({});
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Fetch clinic info from settings endpoint
  const clinicQuery = useQuery({
    queryKey: ["clinicInfo", slug],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/settings`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load clinic information");
      }
      return payload.data as ClinicInfo;
    },
  });

  const updateMutation = useMutation({
    mutationFn: async (data: Partial<ClinicInfo>) => {
      // For now, we'll use a simple approach - in production, you'd create a dedicated endpoint
      const response = await fetch(`/api/proxy/clinic/${slug}/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to update clinic settings");
      }
      return payload.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clinicInfo", slug] });
      queryClient.invalidateQueries({ queryKey: ["dashboard", slug] });
      setIsEditing(false);
      setSuccessMessage("Settings updated successfully!");
      setErrorMessage(null);
      setTimeout(() => setSuccessMessage(null), 5000);
    },
    onError: (error: Error) => {
      setErrorMessage(error.message || "Failed to update settings");
      setSuccessMessage(null);
      setTimeout(() => setErrorMessage(null), 5000);
    },
  });

  const handleEdit = () => {
    if (clinicQuery.data) {
      setFormData(clinicQuery.data);
      setIsEditing(true);
      setSuccessMessage(null);
      setErrorMessage(null);
    }
  };

  const handleCancel = () => {
    setIsEditing(false);
    setFormData({});
    setSuccessMessage(null);
    setErrorMessage(null);
  };

  const handleSave = () => {
    if (!formData.name?.trim()) {
      setErrorMessage("Clinic name is required");
      return;
    }
    updateMutation.mutate(formData);
  };

  const handleChange = (field: keyof ClinicInfo, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const isReadOnly = support?.readOnly || false;
  const clinicData = isEditing ? formData : clinicQuery.data;

  if (clinicQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-blue-600 border-t-transparent"></div>
          <p className="mt-4 text-sm text-gray-600">Loading clinic settings...</p>
        </div>
      </div>
    );
  }

  if (clinicQuery.isError) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
          <AlertCircle className="mx-auto h-12 w-12 text-red-600" />
          <p className="mt-4 text-sm font-medium text-red-900">Failed to load clinic settings</p>
          <p className="mt-2 text-xs text-red-700">{clinicQuery.error?.message || "Unknown error"}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-gray-50">
      {/* Header */}
      <div className="border-b border-gray-200 bg-white px-6 py-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-lg">
              <Settings className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
              <p className="text-sm text-gray-600 mt-1">Manage your clinic information and preferences</p>
            </div>
          </div>
          {!isEditing && !isReadOnly && (
            <button
              onClick={handleEdit}
              className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors shadow-sm"
            >
              <Settings className="w-4 h-4" />
              Edit Settings
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      {successMessage && (
        <div className="mx-6 mt-4 rounded-lg border border-green-200 bg-green-50 p-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-600" />
            <p className="text-sm font-medium text-green-900">{successMessage}</p>
          </div>
        </div>
      )}

      {errorMessage && (
        <div className="mx-6 mt-4 rounded-lg border border-red-200 bg-red-50 p-4">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-red-600" />
            <p className="text-sm font-medium text-red-900">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-4xl">
          <div className="space-y-6">
            {/* Basic Information */}
            <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-200 px-6 py-4">
                <h2 className="text-lg font-semibold text-gray-900">Basic Information</h2>
                <p className="text-sm text-gray-600 mt-1">Clinic name and contact details</p>
              </div>
              <div className="p-6 space-y-5">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    <div className="flex items-center gap-2">
                      <Globe className="w-4 h-4 text-gray-500" />
                      Clinic Name
                    </div>
                  </label>
                  {isEditing ? (
                    <input
                      type="text"
                      value={clinicData?.name || ""}
                      onChange={(e) => handleChange("name", e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none transition-colors"
                      placeholder="Enter clinic name"
                    />
                  ) : (
                    <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-gray-900">
                      {clinicData?.name || "—"}
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    <div className="flex items-center gap-2">
                      <Phone className="w-4 h-4 text-gray-500" />
                      Phone Number
                    </div>
                  </label>
                  {isEditing ? (
                    <input
                      type="tel"
                      value={clinicData?.phone_number || ""}
                      onChange={(e) => handleChange("phone_number", e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none transition-colors"
                      placeholder="+1234567890"
                    />
                  ) : (
                    <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-gray-900">
                      {clinicData?.phone_number || "—"}
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    <div className="flex items-center gap-2">
                      <Phone className="w-4 h-4 text-gray-500" />
                      WhatsApp Number
                    </div>
                  </label>
                  {isEditing ? (
                    <input
                      type="tel"
                      value={clinicData?.whatsapp_number || ""}
                      onChange={(e) => handleChange("whatsapp_number", e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none transition-colors"
                      placeholder="+1234567890"
                    />
                  ) : (
                    <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-gray-900">
                      {clinicData?.whatsapp_number || "—"}
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    <div className="flex items-center gap-2">
                      <MapPin className="w-4 h-4 text-gray-500" />
                      Address
                    </div>
                  </label>
                  {isEditing ? (
                    <textarea
                      value={clinicData?.address || ""}
                      onChange={(e) => handleChange("address", e.target.value)}
                      rows={3}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none transition-colors resize-none"
                      placeholder="Enter clinic address"
                    />
                  ) : (
                    <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-gray-900 whitespace-pre-wrap">
                      {clinicData?.address || "—"}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Preferences */}
            <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-200 px-6 py-4">
                <h2 className="text-lg font-semibold text-gray-900">Preferences</h2>
                <p className="text-sm text-gray-600 mt-1">Timezone and language settings</p>
              </div>
              <div className="p-6 space-y-5">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-gray-500" />
                      Timezone
                    </div>
                  </label>
                  {isEditing ? (
                    <input
                      type="text"
                      value={clinicData?.tz || ""}
                      onChange={(e) => handleChange("tz", e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none transition-colors"
                      placeholder="UTC, America/New_York, etc."
                    />
                  ) : (
                    <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-gray-900">
                      {clinicData?.tz || "UTC"}
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    <div className="flex items-center gap-2">
                      <Languages className="w-4 h-4 text-gray-500" />
                      Default Language
                    </div>
                  </label>
                  {isEditing ? (
                    <select
                      value={clinicData?.default_lang || "en"}
                      onChange={(e) => handleChange("default_lang", e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 outline-none transition-colors bg-white"
                    >
                      <option value="en">English</option>
                      <option value="ar">Arabic</option>
                    </select>
                  ) : (
                    <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-2.5 text-sm text-gray-900">
                      {clinicData?.default_lang === "ar" ? "Arabic" : "English"}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Read-only notice */}
            {isReadOnly && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <div className="flex items-center gap-2">
                  <AlertCircle className="h-5 w-5 text-amber-600" />
                  <p className="text-sm font-medium text-amber-900">
                    You are in read-only mode. Settings cannot be modified during support sessions.
                  </p>
                </div>
              </div>
            )}

            {/* Action buttons */}
            {isEditing && !isReadOnly && (
              <div className="flex items-center justify-end gap-3 rounded-lg border border-gray-200 bg-white px-6 py-4 shadow-sm">
                <button
                  onClick={handleCancel}
                  disabled={updateMutation.isPending}
                  className="rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={updateMutation.isPending || !formData.name?.trim()}
                  className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
                >
                  {updateMutation.isPending ? (
                    <>
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4" />
                      Save Changes
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
