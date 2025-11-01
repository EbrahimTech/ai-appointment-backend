"use server";

import { cookies } from "next/headers";

export async function POST(request: Request) {
  const { slug } = await request.json();
  if (!slug) {
    return new Response(JSON.stringify({ ok: false, error: "INVALID_SLUG" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }
  const store = cookies();
  store.set("clinicSlug", slug, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    expires: new Date(Date.now() + 1000 * 60 * 60 * 24),
  });
  store.delete("supportToken");
  store.delete("supportClinicSlug");
  store.delete("supportExpiresAt");
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
