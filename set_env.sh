#!/bin/bash

# This script sets up the Google Cloud environment by:
# 1. Sourcing variables from the .env file in the project root.
# 2. Checking gcloud authentication status.
# 3. Setting the active gcloud project configuration.
# It must be SOURCED to make the variables available in your current shell.
# Example: source ./set_env.sh

echo "--- Configuring Shell Environment for Google Cloud ---"

# Determine Project Root and .env file path
# This assumes the script might be in a subdirectory (e.g., scripts/) or in the root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ENV_FILE_PROJECT_ROOT="${SCRIPT_DIR}/../.env" # Check for .env in parent directory
ENV_FILE_CURRENT_DIR="./.env" # Check for .env in current directory (if script is in root)

ENV_FILE_TO_USE=""

if [ -f "$ENV_FILE_PROJECT_ROOT" ]; then
  ENV_FILE_TO_USE="$ENV_FILE_PROJECT_ROOT"
elif [ -f "$ENV_FILE_CURRENT_DIR" ]; then
  ENV_FILE_TO_USE="$ENV_FILE_CURRENT_DIR"
fi

# Source .env file if found
if [ -n "$ENV_FILE_TO_USE" ]; then
  echo "Sourcing environment variables from $ENV_FILE_TO_USE..."
  # Using set -a to export all variables defined in the .env file
  # Using POSIX-compliant way to source by temporarily disabling 'nounset' if active
  set -o allexport
  source "$ENV_FILE_TO_USE"
  set +o allexport
  if [ $? -ne 0 ]; then
    echo "Error: Failed to source $ENV_FILE_TO_USE."
    echo "Please check the file for syntax errors."
    return 1
  fi
  echo "Successfully sourced $ENV_FILE_TO_USE."
else
  echo "Error: .env file not found."
  echo "Please copy .env.example to .env in the project root and fill in the required values."
  return 1
fi

# --- Authentication Check ---
echo "Checking gcloud authentication status..."
if gcloud auth print-access-token > /dev/null 2>&1; then
  echo "gcloud is authenticated."
else
  echo "Error: gcloud is not authenticated."
  echo "Please log in by running: gcloud auth login"
  return 1
fi
# --- --- --- --- --- ---

# --- Set gcloud Project Configuration ---
if [ -z "$COMMON_GOOGLE_CLOUD_PROJECT" ]; then
  echo "Error: COMMON_GOOGLE_CLOUD_PROJECT is not set in your .env file."
  echo "Please ensure it is defined in $ENV_FILE_TO_USE."
  return 1
fi

echo "Setting active gcloud project to: $COMMON_GOOGLE_CLOUD_PROJECT"
gcloud config set project "$COMMON_GOOGLE_CLOUD_PROJECT" --quiet
if [ $? -ne 0 ]; then
  echo "Error: Failed to set gcloud project to $COMMON_GOOGLE_CLOUD_PROJECT."
  echo "Please ensure the project ID is correct and you have permissions."
  return 1
fi
echo "Successfully set active gcloud project."
# --- --- --- --- --- ---

echo "--- Google Cloud environment setup complete ---"
