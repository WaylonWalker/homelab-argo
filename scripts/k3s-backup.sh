#!/bin/bash
set -euo pipefail

# Configuration
BACKUP_DIR="/mnt/vault/nfs/general/backup/k3s"
DATE=$(date +'%Y-%m-%d')
BACKUP_FILE="${BACKUP_DIR}/k3s-backup-${DATE}.tar.gz"

# List of items to backup
ITEMS=(
	"/var/lib/rancher/k3s/server/token"
	"/var/lib/rancher/k3s/server/manifests"
	"/var/lib/rancher/k3s/server/db"
)

# Ensure the backup directory exists
mkdir -p "$BACKUP_DIR"

# Create the backup archive
tar -czvf "$BACKUP_FILE" "${ITEMS[@]}"

# Optionally, log the backup operation
echo "Backup completed on ${DATE}: ${BACKUP_FILE}"
