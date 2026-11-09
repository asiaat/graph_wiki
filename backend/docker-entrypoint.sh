#!/bin/sh
# Container entrypoint.
#
# The image runs as the unprivileged `kuzuwiki` user, but the data volumes are
# bind-mounted from the host and are therefore owned by whoever runs compose.
# As root we fix the ownership of the writable paths once, then drop
# privileges for the actual process.

set -e

# These must match the bind-mount targets in docker-compose.yml exactly.
# Getting this wrong leaves the app user unable to write the directory, which
# silently breaks quarantine (the Gatekeeper cannot file a slop document).
DATA_DIRS="/data/kuzudb /data/wiki /data/raw_vault /data/quarantine /data/projects"

for dir in $DATA_DIRS; do
    mkdir -p "$dir" 2>/dev/null || true
    chown -R kuzuwiki:kuzuwiki "$dir" 2>/dev/null || true
done

# The domain packs and the application code are read-only for the app user.
chown -R kuzuwiki:kuzuwiki /app 2>/dev/null || true

exec gosu kuzuwiki "$@"
