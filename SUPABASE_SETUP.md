# Supabase setup

Use one Supabase project for Vercel and Render. Configure the project URL, a publishable key for browser sign-in, and a private `sb_secret_*` server API key in server-only Vercel and Render variables. The backend authentication helper sends a new secret key as `apikey` only. Legacy `SUPABASE_SERVICE_ROLE_KEY` JWT deployments remain supported with both `apikey` and `Authorization: Bearer`. Never put either server credential in browser code or logs.

Create private Storage buckets `uploads`, `royal-scout-artifacts`, and `fixtures`; migration `0006_private_storage_buckets.sql` does this. Keep them private. Apply migrations `0001` through `0007` in order using the Supabase SQL migration workflow. `0007` restricts queue SECURITY DEFINER RPC execution to the `service_role`. Production users authenticate via Supabase Auth; signed-upload issuance is server-side and object paths are scoped to project/dataset IDs. Worker source access accepts only configured upload bucket or fixtures; outputs are written to the artifact bucket.

Do not grant anonymous access to queue rows or private objects. The service key is only for trusted server-side operations. Dashboard authenticated-user requests use the user's Supabase session, not the server API key. `/health/ready` checks table and bucket reachability without returning credentials.
