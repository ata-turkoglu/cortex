#!/bin/sh
set -eu

required_models="${CORTEX_OLLAMA_REQUIRED_MODELS:-bge-m3:latest}"

for model in $(printf '%s' "$required_models" | tr ',' ' '); do
  if ollama list | awk 'NR > 1 { print $1 }' | grep -Fqx -- "$model"; then
    printf 'Cortex Ollama model already present: %s\n' "$model"
  else
    printf 'Cortex Ollama model missing; pulling: %s\n' "$model"
    ollama pull "$model"
  fi
done
