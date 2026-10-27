#!/bin/sh
# Container entrypoint.
#
# The image runs as the unprivileged `kuzuwiki` user, but the data volumes are
# bind-mounted from the host and are therefore owned by whoever runs compose.
# As root we fix the ownership of the writable paths once, then drop
# privileges for the actual process.

set -e

DATA_DIRS="/data/kuzudb /data/wiki /data/raw_vault /quarantine/slop"

for dir in $DATA_DIRS; do
    mkdir -p "$dir" 2>/dev/null || true
    chown -R kuzuwiki:kuzuwiki "$dir" 2>/dev/null || true
done

# The domain packs and the application code are read-only for the app user.
chown -R kuzuwiki:kuzuwiki /app 2>/dev/null || true

exec gosu kuzuwiki "$@"
