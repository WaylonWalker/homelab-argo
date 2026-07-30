#!/usr/bin/env bash
set -ueo pipefail

NAME=${1:-"{{name}}"}

# Find app location using fd (only directories, exact name match)
export APP_PATH=$(fdfind -t d "^${NAME}$" k8s | head -n1)
if [ -z "$APP_PATH" ]; then
	echo "Error: Could not find application directory for ${NAME}"
	echo "Expected to find ${NAME} somewhere under the apps/ directory"
	exit 1
fi

echo "$APP_PATH"
