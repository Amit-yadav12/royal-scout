type SupabaseProfileLookup = {
  from: (table: "profiles") => {
    select: (columns: "id,role") => {
      eq: (column: "id", value: string) => {
        maybeSingle: () => PromiseLike<{ data: { id?: string; role?: string } | null; error: unknown }>;
      };
    };
  };
};

export type StaffRole = "viewer" | "admin";

export type StaffAccess =
  | { status: "verified"; role: StaffRole; canUpload: boolean; message: null }
  | { status: "profile_missing"; role: null; canUpload: false; message: string }
  | { status: "invalid_role"; role: null; canUpload: false; message: string }
  | { status: "lookup_failed"; role: null; canUpload: false; message: string };

const VALID_ROLES: readonly StaffRole[] = ["viewer", "admin"];

/** Read only the signed-in user's own profile; distinguish absent data from DB/RLS failures. */
export async function getStaffAccess(client: unknown, userId: string): Promise<StaffAccess> {
  try {
    const { data, error } = await (client as SupabaseProfileLookup)
      .from("profiles").select("id,role").eq("id", userId).maybeSingle();
    if (error) {
      return { status: "lookup_failed", role: null, canUpload: false,
        message: "Royal Scout could not verify your profile from Supabase. Retry, then ask an administrator to check profile read access." };
    }
    if (!data || data.id !== userId) {
      return { status: "profile_missing", role: null, canUpload: false,
        message: "Your authenticated account has no matching staff profile. Ask the platform owner to run the profile backfill or initial-admin bootstrap." };
    }
    if (!VALID_ROLES.includes(data.role as StaffRole)) {
      return { status: "invalid_role", role: null, canUpload: false,
        message: "Your staff profile has an unsupported role value. Ask a platform administrator to repair it." };
    }
    const role = data.role as StaffRole;
    return { status: "verified", role, canUpload: role === "admin", message: null };
  } catch {
    return { status: "lookup_failed", role: null, canUpload: false,
      message: "Royal Scout could not contact Supabase to verify your profile. Retry when the service is available." };
  }
}

/** Compatibility helper for server gates; every non-verified result fails closed. */
export async function getStaffRole(client: unknown, userId: string): Promise<StaffRole | null> {
  const access = await getStaffAccess(client, userId);
  return access.status === "verified" ? access.role : null;
}

/** Only the verified administrator profile may upload or process datasets. */
export async function mayManageIngestion(client: unknown, userId: string): Promise<boolean> {
  const access = await getStaffAccess(client, userId);
  return access.status === "verified" && access.canUpload;
}

/** Staff administration is deliberately narrower than ingestion permissions. */
export async function isPlatformAdmin(client: unknown, userId: string): Promise<boolean> {
  return (await getStaffRole(client, userId)) === "admin";
}
