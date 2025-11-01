"use server";

import { cookies } from "next/headers";

export async function POST() {
  const store = cookies();
  for (const key of ["accessToken", "refreshToken", "clinicSlug", "hqRole", "supportToken", "supportClinicSlug", "supportExpiresAt"]) {
    store.delete(key);
  }
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
