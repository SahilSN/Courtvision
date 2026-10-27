"""Small offline Live artifacts; atomic worker writes, bounded viewer reads."""

from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile


def read_json(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Live artifact exceeds size limit')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Live artifact must be an object')
    return value


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    payload = json.dumps(value, indent=2, allow_nan=False) + '\n'
    if len(payload.encode()) > 2_000_000:
        raise ValueError('Live artifact exceeds size limit')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
