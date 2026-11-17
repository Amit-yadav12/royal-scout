export function existingAdminOtpOptions(emailRedirectTo: string) {
  return {
    shouldCreateUser: false,
    emailRedirectTo,
  } as const;
}
