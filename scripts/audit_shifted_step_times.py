"""
List logbooks whose step times were probably shifted by a re-save.

Before the lab time zone was introduced, opening a saved logbook in the
dashboard showed the step times in UTC while the run start was shown in local
time; saving it again moved every step one (winter) or two (summer) hours
earlier. Such a logbook typically has steps that start before the run itself,
by about the UTC offset of the run's date.

Read only: the script searches and reads archives and writes nothing to NOMAD.
It prints one CSV line per suspicious logbook, for the lab to check by hand.

    uv run python scripts/audit_shifted_step_times.py \\
        --url https://<oasis>/nomad-oasis/api/v1 --token <access token>

The token is that of a user who can see the uploads (in the NOMAD GUI: your
name, then *API token*), or set NOMAD_TOKEN.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta

import requests

LOGBOOKS = ('SAPLDLogbook', 'LAPLDLogbook', 'SPSLogbook')
# A step starting this much before the run is suspicious.
TOLERANCE = timedelta(minutes=30)


def _parse(value):
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


def _entries(session, url):
    after = None
    while True:
        body = {
            'owner': 'visible',
            'query': {'entry_type:any': list(LOGBOOKS)},
            'pagination': {'page_size': 100, 'page_after_value': after},
            'required': {'include': ['entry_id', 'upload_id', 'mainfile']},
        }
        response = session.post(f'{url}/entries/query', json=body, timeout=60)
        response.raise_for_status()
        result = response.json()
        yield from result['data']
        after = result['pagination'].get('next_page_after_value')
        if not after:
            return


def suspicious(data: dict) -> list[str]:
    """Why the steps of this logbook look shifted; empty if they do not."""
    start = _parse(data.get('datetime'))
    if start is None:
        return []
    reasons = []
    for index, step in enumerate(data.get('steps') or []):
        step_start = _parse(step.get('start_time'))
        if step_start is not None and start - step_start >= TOLERANCE:
            reasons.append(
                f'step {index + 1} starts {start - step_start} before the run'
            )
    return reasons


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--url', required=True, help='NOMAD API, ending in /api/v1')
    parser.add_argument('--token', default=os.environ.get('NOMAD_TOKEN'))
    args = parser.parse_args(argv)
    session = requests.Session()
    if args.token:
        session.headers['Authorization'] = f'Bearer {args.token}'
    url = args.url.rstrip('/')
    out = csv.writer(sys.stdout)
    out.writerow(['upload_id', 'entry_id', 'mainfile', 'run start', 'reasons'])
    for entry in _entries(session, url):
        response = session.get(f'{url}/entries/{entry["entry_id"]}/archive', timeout=60)
        if not response.ok:
            continue
        data = response.json()['data']['archive'].get('data') or {}
        reasons = suspicious(data)
        if reasons:
            out.writerow(
                [
                    entry['upload_id'],
                    entry['entry_id'],
                    entry['mainfile'],
                    data.get('datetime'),
                    '; '.join(reasons),
                ]
            )


if __name__ == '__main__':
    main()
