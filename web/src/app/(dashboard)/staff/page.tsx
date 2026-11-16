import { notFound } from "next/navigation";

/** Staff administration is intentionally not part of the public read-only dashboard. */
export default function StaffAdministrationPage(): never {
  notFound();
}
