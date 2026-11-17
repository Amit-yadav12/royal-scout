export function existingStaffOtpOptions(emailRedirectTo: string) {
  return {
    shouldCreateUser: false,
    emailRedirectTo,
  } as const;
}

/** Roles an authenticated platform admin may assign; never sourced from email. */
export const ASSIGNABLE_STAFF_ROLES = ["viewer", "analyst", "scout", "admin"] as const;
export type AssignableStaffRole = typeof ASSIGNABLE_STAFF_ROLES[number];

export function isAssignableStaffRole(role: unknown): role is AssignableStaffRole {
  return typeof role === "string" && ASSIGNABLE_STAFF_ROLES.includes(role as AssignableStaffRole);
}

/** Backwards-compatible name for the admin-only invitation endpoint. */
export const INVITABLE_STAFF_ROLES = ASSIGNABLE_STAFF_ROLES;
export type InvitableStaffRole = AssignableStaffRole;
export const isInvitableStaffRole = isAssignableStaffRole;
