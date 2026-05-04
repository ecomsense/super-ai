#!/bin/bash
# Copy SSH public key to remote server (65.20.88.130)
# Usage: ./scripts/setup-ssh-key.sh

REMOTE_USER="harinath"
REMOTE_HOST="65.20.88.130"
KEY_FILE="$HOME/.ssh/id_ed25519.pub"

echo "Copying SSH key to ${REMOTE_USER}@${REMOTE_HOST}..."
ssh-copy-id -i "$KEY_FILE" "${REMOTE_USER}@${REMOTE_HOST}"

if [ $? -eq 0 ]; then
    echo "Success! You can now SSH without password:"
    echo "  ssh harinath.r"
else
    echo "Failed. Check your password and try again."
fi
