#!/bin/bash

# Set default values if not provided
PUID=${PUID:-1000}
PGID=${PGID:-1000}
UMASK=${UMASK:-022}

echo "🚀 Starting Combiner with PUID=$PUID, PGID=$PGID, UMASK=$UMASK"

# Create group if it doesn't exist
if ! getent group $PGID > /dev/null 2>&1; then
    echo "📝 Creating group with GID $PGID"
    groupadd -g $PGID combiner
else
    GROUP_NAME=$(getent group $PGID | cut -d: -f1)
    echo "✅ Using existing group: $GROUP_NAME (GID $PGID)"
fi

# Create user if it doesn't exist
if ! getent passwd $PUID > /dev/null 2>&1; then
    echo "📝 Creating user with UID $PUID"
    useradd -u $PUID -g $PGID -d /app -s /bin/bash combiner
else
    USER_NAME=$(getent passwd $PUID | cut -d: -f1)
    echo "✅ Using existing user: $USER_NAME (UID $PUID)"
fi

# Set umask
umask $UMASK
echo "🔒 Set umask to $UMASK"

# Fix ownership of app directory and config directory
echo "🔧 Setting ownership of /app and /config"
chown -R $PUID:$PGID /app /config

# Switch to the specified user and run the command
echo "🎬 Starting application as UID $PUID, GID $PGID"
exec gosu $PUID:$PGID "$@"
