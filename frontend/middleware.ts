import { NextRequest, NextResponse } from "next/server";

const clinicPattern = /^\/c\/([^/]+)(\/.*)?$/;

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname.startsWith("/api/")) {
    return NextResponse.next();
  }

  const accessToken = request.cookies.get("accessToken");
  if (pathname.startsWith("/login")) {
    if (accessToken) {
      return NextResponse.redirect(new URL("/select-clinic", request.url));
    }
    return NextResponse.next();
  }

  if (pathname.startsWith("/select-clinic")) {
    if (!accessToken) {
      return NextResponse.redirect(new URL("/login", request.url));
    }
    return NextResponse.next();
  }

  if (pathname.startsWith("/hq")) {
    if (!accessToken) {
      return NextResponse.redirect(new URL("/login", request.url));
    }
    const hqRole = request.cookies.get("hqRole")?.value;
    if (!hqRole) {
      return NextResponse.redirect(new URL("/login", request.url));
    }
    return NextResponse.next();
  }

  const clinicMatch = pathname.match(clinicPattern);
  if (clinicMatch) {
    if (!accessToken) {
      return NextResponse.redirect(new URL("/login", request.url));
    }
    const slug = clinicMatch[1];
    const storedSlug = request.cookies.get("clinicSlug")?.value;
    const hqRole = request.cookies.get("hqRole")?.value;
    
    // HQ staff (SUPERADMIN/OPS) can access any clinic directly without clinicSlug cookie
    // The backend middleware will handle the authorization
    if (hqRole && (hqRole === "SUPERADMIN" || hqRole === "OPS")) {
      // Allow access - backend will verify HQ role
      return NextResponse.next();
    }
    
    // Regular users need clinicSlug cookie to match
    if (!storedSlug || storedSlug !== slug) {
      return NextResponse.redirect(new URL("/select-clinic", request.url));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
