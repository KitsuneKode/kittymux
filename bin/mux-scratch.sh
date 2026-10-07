#!/usr/bin/env bash
# Compatibility entry point; argv orchestration lives in the tested CLI.
exec "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/kittymux" workflow scratch "$@"
