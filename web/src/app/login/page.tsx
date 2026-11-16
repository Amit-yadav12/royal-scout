import { redirect } from "next/navigation";

/** The dashboard is public; old sign-in links return visitors to the homepage. */
export default function LoginPage() {
  redirect("/");
}
