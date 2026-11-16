type SupabaseProfileLookup = {
  from: (table: "profiles") => {
    select: (columns: "role") => {
      eq: (column: "id", value: string) => {
        maybeSingle: () => PromiseLike<{ data: { role?: string } | null; error: unknown }>;
      };
    };
  };
};

/** Only explicitly elevated staff may create or retry ingestion jobs. */
export async function mayManageIngestion(client: unknown, userId: string): Promise<boolean> {
  try {
    const { data, error } = await (client as SupabaseProfileLookup).from("profiles").select("role").eq("id", userId).maybeSingle();
    return !error && ["analyst", "scout", "admin"].includes(data?.role ?? "");
  } catch {
    return false;
  }
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
