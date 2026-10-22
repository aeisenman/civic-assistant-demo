#!/usr/bin/env bash
# Pulls the Ollama models this project's tiers map to and builds a long-context
# variant for document extraction. Run once on the dev machine; the API talks to
# Ollama at host.docker.internal:11434. Depends on: ollama on PATH and running.
set -euo pipefail

MODELS=("qwen2.5:3b" "qwen2.5:7b" "nomic-embed-text")
LONG_CTX_MODEL="qwen2.5:7b-32k"

have() { ollama list | awk 'NR>1 {print $1}' | grep -qx "$1"; }

for m in "${MODELS[@]}"; do
  # `ollama list` prints "qwen2.5:3b" but "nomic-embed-text:latest"; check both.
  if have "$m" || have "${m}:latest"; then
    echo "ok      $m (already present)"
  else
    echo "pulling $m"
    ollama pull "$m"
  fi
done

# Ollama defaults to a 4k context window, which truncates permit PDFs. The
# EXTRACT tier points at this 32k variant instead.
if have "$LONG_CTX_MODEL" || have "${LONG_CTX_MODEL}:latest"; then
  echo "ok      $LONG_CTX_MODEL (already present)"
else
  echo "creating $LONG_CTX_MODEL"
  tmp="$(mktemp -d)"
  printf 'FROM qwen2.5:7b\nPARAMETER num_ctx 32768\n' > "$tmp/Modelfile"
  ollama create "$LONG_CTX_MODEL" -f "$tmp/Modelfile"
  rm -rf "$tmp"
fi

echo
echo "models available:"
ollama list | awk 'NR>1 {print "  " $1}'
