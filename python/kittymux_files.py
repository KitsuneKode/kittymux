"""Bounded JSON boundary reads. Existing file formats and unknown keys stay compatible."""
import json

def read_json(path, default=None, limit=2 * 1024 * 1024, root=dict):
    try:
        with open(path, 'rb') as f:
            raw = f.read(limit + 1)
        if len(raw) > limit:
            return default
        obj = json.loads(raw)
        return obj if isinstance(obj, root) else default
    except (OSError, ValueError, TypeError, RecursionError):
        return default

def positive_id(value):
    return isinstance(value, int) and (not isinstance(value, bool)) and (value > 0)
