#!/bin/sh
set -eu
umask 077
cd "${RELEASE_DIR:-/opt/calendar-invites}"
destination=${BACKUP_DIR:-/var/backups/calendar-invites}
mkdir -p "$destination"
file="$destination/calendar-invites-$(date -u +%Y%m%dT%H%M%SZ).dump"
# Local container socket auth; never put passwords on command lines or in output.
docker compose exec -T postgres pg_dump -U calendar_invites -d calendar_invites -Fc > "$file.partial"
docker compose exec -T postgres pg_restore --list < "$file.partial" > /dev/null
mv "$file.partial" "$file"
printf 'Backup verified: %s\n' "$file"
# Retention/offsite destination are operator policy; do not silently delete backups.
