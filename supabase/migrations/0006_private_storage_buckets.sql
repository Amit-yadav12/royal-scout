-- Private object-storage buckets used by the signed-upload + processing-worker flow.
-- Upload signatures are minted server-side; the browser never receives a service-role key.
insert into storage.buckets (id, name, public)
values
  ('uploads', 'uploads', false),
  ('royal-scout-artifacts', 'royal-scout-artifacts', false),
  ('fixtures', 'fixtures', false)
on conflict (id) do update set public = excluded.public;

-- No anonymous storage policies are created. The Vercel server signs upload URLs
-- after checking the authenticated staff session. The worker uses the service-role
-- key to download sources and publish private analytical artefacts.
