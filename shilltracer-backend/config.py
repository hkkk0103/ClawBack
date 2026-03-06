import os
from pathlib import Path


def _load_local_env() -> None:
    env_path = Path(__file__).resolve().parent / '.env'
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()


def _parse_csv_env(name: str) -> list[str]:
    raw = os.getenv(name, '')
    return [item.strip() for item in raw.split(',') if item.strip()]


MORALIS_API_KEYS = _parse_csv_env('MORALIS_API_KEYS')
if not MORALIS_API_KEYS:
    single = os.getenv('MORALIS_API_KEY', '').strip()
    if single:
        MORALIS_API_KEYS = [single]

BSCSCAN_API_KEY = os.getenv('BSCSCAN_API_KEY', '').strip()
MORALIS_API_BASE = 'https://deep-index.moralis.io/api/v2.2'
BSCSCAN_API_BASE = 'https://api.bscscan.com/api'


def validate_backend_env() -> None:
    if not MORALIS_API_KEYS:
        raise RuntimeError(
            'Missing Moralis API key. Set MORALIS_API_KEYS=key1,key2 or MORALIS_API_KEY=key1 in shilltracer-backend/.env'
        )
