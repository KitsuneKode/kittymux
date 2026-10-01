#!/usr/bin/env bash
# mux-edge.sh — cycle THIS kitty window's tab bar edge (left → bottom → top → right).
# Kept so existing key bindings keep working; the logic lives in `kittymux layout`
# (per-instance, survives config reloads). It used to rewrite one global include file and
# reload every kitty at once.
exec "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/kittymux" layout edge cycle
