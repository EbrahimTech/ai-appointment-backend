from __future__ import annotations

import types

from django.contrib import admin

APP_ORDER = [
    "clinics",
    "patients",
    "conversations",
    "appointments",
    "channels",
    "auth",
]

MODEL_ORDER = {
    "clinics": ["clinic", "clinicservice", "servicehours"],
    "patients": ["patient", "patientnote"],
    "conversations": ["conversation", "conversationmessage", "sessionstate"],
    "channels": ["outboxmessage"],
    "auth": ["user", "group"],
}


_original_get_app_list = admin.site.get_app_list


def _ordered_app_list(self, request, app_label=None):
    app_list = _original_get_app_list(request, app_label=app_label)
    app_index = {label: idx for idx, label in enumerate(APP_ORDER)}
    app_list.sort(key=lambda app: app_index.get(app["app_label"], 999))

    for app in app_list:
        model_order = MODEL_ORDER.get(app["app_label"])
        if not model_order:
            continue
        model_index = {name: idx for idx, name in enumerate(model_order)}
        app["models"].sort(
            key=lambda model: model_index.get(model["object_name"].lower(), 999)
        )

    return app_list


admin.site.get_app_list = types.MethodType(_ordered_app_list, admin.site)
admin.site.site_header = "AI Appointment Admin"
admin.site.site_title = "AI Appointment Admin"
admin.site.index_title = "Clinic Operations"
