export function existingStaffOtpOptions(emailRedirectTo: string) {
  return {
    shouldCreateUser: false,
    emailRedirectTo,
  } as const;
}

export const INVITABLE_STAFF_ROLES = ["viewer", "analyst", "scout"] as const;
export type InvitableStaffRole = typeof INVITABLE_STAFF_ROLES[number];

export function isInvitableStaffRole(role: unknown): role is InvitableStaffRole {
  return typeof role === "string" && INVITABLE_STAFF_ROLES.includes(role as InvitableStaffRole);
}
