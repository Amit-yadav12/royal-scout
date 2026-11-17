type SupabaseProfileLookup = {
  from: (table: "profiles") => {
    select: (columns: "role") => {
      eq: (column: "id", value: string) => {
        maybeSingle: () => PromiseLike<{ data: { role?: string } | null; error: unknown }>;
      };
    };
  };
};

export type StaffRole = "viewer" | "analyst" | "scout" | "admin";

export async function getStaffRole(client: unknown, userId: string): Promise<StaffRole | null> {
  try {
    const { data, error } = await (client as SupabaseProfileLookup).from("profiles").select("role").eq("id", userId).maybeSingle();
    if (error || !["viewer", "analyst", "scout", "admin"].includes(data?.role ?? "")) return null;
    return data!.role as StaffRole;
  } catch {
    return null;
  }
}

/** Only explicitly elevated staff may create or retry ingestion jobs. */
export async function mayManageIngestion(client: unknown, userId: string): Promise<boolean> {
  return ["analyst", "scout", "admin"].includes((await getStaffRole(client, userId)) ?? "");
}

/** Staff administration is deliberately narrower than ingestion permissions. */
export async function isPlatformAdmin(client: unknown, userId: string): Promise<boolean> {
  try {
    const { data, error } = await (client as SupabaseProfileLookup).from("profiles").select("role").eq("id", userId).maybeSingle();
    return !error && data?.role === "admin";
  } catch {
    return false;
  }
}
