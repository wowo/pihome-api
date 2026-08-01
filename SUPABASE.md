# Supabase cutover notes

Project: `pihome` (`agxpttxixydvttjnxhbn`, eu-central-1)

## config.yml

```yaml
storing:
  supabase:
    url: 'https://agxpttxixydvttjnxhbn.supabase.co'
    service_role_key: '<from Supabase → Settings → API>'
    anon_key: '<anon/publishable key>'
```

## Cron on the Pi

Replace sensor crons with:

```
* * * * * cd /var/www/pihome-api && /usr/bin/python pihome.py --flush-outbox
*/5 * * * * cd /var/www/pihome-api && /usr/bin/python pihome.py --sync-switch-state
```

## Migrate Mongo data

From a host that can reach Mongo + Supabase:

```bash
SUPABASE_URL=https://agxpttxixydvttjnxhbn.supabase.co \
SUPABASE_SERVICE_ROLE_KEY=... \
MONGO_URI='mongodb://...' \
python3 cli/migrate_mongo_to_supabase.py
```

Or fill `config.yml` and run without env vars.

## Auth

- Mutating routes require `Authorization: Bearer <supabase jwt>` unless the client is on LAN/localhost.
- History attribution: JWT email, or `X-PiHome-User` on LAN.
