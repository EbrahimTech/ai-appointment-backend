"use server";

import { cookies } from "next/headers";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export async function POST() {
  const cookieStore = cookies();
  const access = cookieStore.get("accessToken");
  const supportToken = cookieStore.get("supportToken");

  if (!access || !supportToken) {
    cookieStore.delete("supportToken");
    cookieStore.delete("supportClinicSlug");
    cookieStore.delete("supportExpiresAt");
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }

  const response = await fetch(`${BACKEND_URL}/hq/support/stop`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${access.value}`,
    },
    body: JSON.stringify({ support_token: supportToken.value }),
  });
  const payload = await response.json().catch(() => ({}));

  cookieStore.delete("supportToken");
  cookieStore.delete("supportClinicSlug");
  cookieStore.delete("supportExpiresAt");

  if (!response.ok || payload?.ok === false) {
    return new Response(JSON.stringify(payload), {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
