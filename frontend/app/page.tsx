import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export default function Home() {
  const cookieStore = cookies();
  const accessToken = cookieStore.get("accessToken")?.value;
  const hqRole = cookieStore.get("hqRole")?.value;

  // If user is already logged in, redirect based on their role
  if (accessToken) {
    // HQ staff should go directly to /hq
    if (hqRole && (hqRole === "SUPERADMIN" || hqRole === "OPS")) {
      redirect("/hq");
    }
    // Regular users go to select-clinic
    redirect("/select-clinic");
  }

  // Not logged in, go to login
  redirect("/login");
}
