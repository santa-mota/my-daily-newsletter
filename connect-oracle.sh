#!/bin/bash
# Quick SSH connection script for Oracle Cloud instance

# Instance details
PUBLIC_IP="138.2.233.76"
FQDN="newsletter-bot.subnet03262339.vcn03262339.oraclevcn.com"
SSH_KEY="/Users/shamahap/Desktop/Training/personal/my-daily-newsletter/ssh keys/ssh-key-2026-03-27-private.key"

# Check if key exists
if [ ! -f "$SSH_KEY" ]; then
    echo "❌ SSH key not found at: $SSH_KEY"
    exit 1
fi

# Check key permissions
PERMS=$(stat -f "%OLp" "$SSH_KEY")
if [ "$PERMS" != "600" ]; then
    echo "🔧 Fixing SSH key permissions..."
    chmod 600 "$SSH_KEY"
    echo "✓ Permissions set to 600"
fi

echo "================================================"
echo "Oracle Cloud SSH Connection"
echo "================================================"
echo ""
echo "🔌 Connecting to: ubuntu@$PUBLIC_IP"
echo "🌐 FQDN: $FQDN"
echo "🔑 Using key: ssh-key-2026-03-27-private.key"
echo ""

# Connect
ssh -i "$SSH_KEY" ubuntu@"$PUBLIC_IP"
