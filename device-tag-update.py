#!/usr/bin/env python
# coding: utf-8

"""
Update device tags by MAC address from a CSV file.

Input:
  - CSV with columns "mac_address" (or "mac") and "tag" (or "device_tag"). 
    Duplicate MACs in CSV are de-duplicated (first row kept); a warning is printed.
  - MACs are normalized (lowercase, colon-separated, e.g. aa:bb:cc:dd:ee:ff)
    for both CSV and GraphQL results.

Flow:
  - Fetches all registered devices with a single paginated GraphQL query.
  - Matches CSV rows to devices by normalized MAC; no further GraphQL per row.
  - A device can have multiple MACs (macAddresses). Any one of them in the CSV
    matches that device; use whichever MAC you have (e.g. primary NIC, WiFi, etc.).
  - Dry-run (default): prints a table of matched devices, current tag, new tag,
    and status (Will update / No change / device not found / etc.). No API writes.
  - Apply (--dry-run false): for each matched row where current tag != new tag,
    sends PUT to /api/v2/registered-device/{id} to update the tag. Entries with
    same existing and new tag are skipped (status "No change").

Duplicate MACs:
  - If the same MAC appears on multiple devices in GraphQL results, a warning
    is printed. Apply is blocked only when such a duplicate MAC is also present
    in the CSV (ambiguous which device to update). Non-overlapping duplicates
    only trigger a warning; apply continues.

Auth:
  - Uses lib.common getToken(apiKey, apiSecret). Credentials via --env, --apiKey,
    --apiSecret, or environment variables.
"""

from lib.common import API_KEY, API_SECRET, API_HOST, getToken, booleanString
import argparse
import csv
import os
import sys

from dotenv import load_dotenv
from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport
import requests


REGISTERED_DEVICE_API = '/api/v2/registered-device'

# Query for all devices (paginated). Only fields needed for display and matching.
LIST_REGISTERED_DEVICES = gql(
    """
    query ListRegisteredDevices($payload: GetRegisteredDevicesPayloadDto, $limit: Int, $nextToken: String) {
      registeredDevices(payload: $payload, limit: $limit, nextToken: $nextToken) {
        list {
          id
          deviceModel
          deviceName
          deviceTag {
            id
            displayName
          }
          macAddresses
          userDevices {
            user { id }
            lastLoginAt
          }
        }
        nextToken
      }
    }
    """
)


def _bearer_token(id_token):
    """Ensure token has exactly one 'Bearer ' prefix."""
    if id_token.startswith('Bearer '):
        return id_token
    return f'Bearer {id_token}'


def gqlinit(id_token):
    transport = AIOHTTPTransport(
        url=f'{API_HOST}/api/graphql',
        headers={
            'Authorization': _bearer_token(id_token),
            'Idtoken': id_token,    # Add for compatibility
            'Content-Type': 'application/json'
            },
    )
    return Client(transport=transport, fetch_schema_from_transport=False)


def gql_exec(client, query, variables):
    return client.execute(query, variable_values=variables)


def _auth_headers(id_token):
    return {
        'Content-Type': 'application/json',
        'Authorization': _bearer_token(id_token),
        'Idtoken': id_token,    # Add for compatibility
    }


def put_device_tag(id_token, device_id, device_tag, device_name=None):
    """PUT device tag (and optionally name). Returns response or raises."""
    url = f'{API_HOST}{REGISTERED_DEVICE_API}/{device_id}'
    body = {'deviceTag': device_tag}
    if device_name is not None:
        body['deviceName'] = device_name
    resp = requests.put(url, headers=_auth_headers(id_token), json=body)
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise Exception(f'PUT {resp.status_code}: {detail}')
    return resp.json() if resp.text else {}


def _tag_display(tag_obj):
    """Extract display string from deviceTag object: prefer displayName, fall back to id."""
    if not tag_obj:
        return ''
    return tag_obj.get('displayName') or tag_obj.get('id') or ''


def _normalize_mac(mac):
    """
    Normalize MAC to lowercase colon-separated format when possible.
    Example: AA-BB-CC-DD-EE-FF -> aa:bb:cc:dd:ee:ff
    """
    raw = (mac or '').strip().lower()
    hex_only = ''.join(ch for ch in raw if ch in '0123456789abcdef')
    if len(hex_only) == 12:
        return ':'.join(hex_only[i:i + 2] for i in range(0, 12, 2))
    return raw


def fetch_all_registered_devices(client, page_size=500):
    """
    Run one paginated GraphQL query until all pages are fetched. Returns list of device dicts.
    Uses empty payload so no filter (all devices); if API requires payload, uses minimal.
    """
    all_devices = []
    next_token = None
    while True:
        variables = {
            'limit': page_size,
            'nextToken': next_token,
        }
        result = gql_exec(client, LIST_REGISTERED_DEVICES, variables)
        reg = result.get('registeredDevices') or {}
        items = reg.get('list') or []
        all_devices.extend(items)
        next_token = reg.get('nextToken')
        if not next_token:
            break
    return all_devices


def build_mac_to_device(devices):
    """
    Map normalized MAC -> device. One device can have multiple MACs; each maps to that device.
    Returns (mac_to_device, duplicate_backend_macs).
    Duplicate detection happens after normalization.
    """
    mac_to_device = {}
    duplicate_backend_macs = {}
    for dev in devices:
        dev_id = dev.get('id', '')
        for mac in dev.get('macAddresses') or []:
            norm = _normalize_mac(mac)
            if not norm:
                continue
            if norm in mac_to_device:
                prev_id = (mac_to_device[norm] or {}).get('id', '')
                if prev_id != dev_id:
                    duplicate_backend_macs.setdefault(norm, set()).update({prev_id, dev_id})
            else:
                mac_to_device[norm] = dev
    return mac_to_device, duplicate_backend_macs


def _device_display_info(device, search_mac):
    """From device and search MAC, derive: mac_matched, device_name, device_model, device_tag, user_id, last_login."""
    if not device:
        return {'mac_matched': False, 'device_name': '', 'device_model': '', 'device_tag': '', 'user_id': '', 'last_login': ''}
    macs = [_normalize_mac(m) for m in (device.get('macAddresses') or [])]
    search_norm = _normalize_mac(search_mac)
    mac_matched = search_norm in macs
    ud = (device.get('userDevices') or [])
    first_user = ud[0] if ud else {}
    user_id = (first_user.get('user') or {}).get('id') or ''
    last_login = first_user.get('lastLoginAt') or ''
    return {
        'mac_matched': mac_matched,
        'device_name': (device.get('deviceName') or '')[:64],
        'device_model': (device.get('deviceModel') or '')[:48],
        'device_tag': (_tag_display(device.get('deviceTag')))[:32],
        'user_id': (user_id or '')[:32],
        'last_login': (last_login or '')[:24],
    }


def load_csv(path):
    """
    Load CSV with columns mac_address (or mac) and tag.
    Returns list of dicts: [{'mac': str, 'tag': str}, ...].
    """
    rows = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        # Normalize headers: strip, lower
        if not reader.fieldnames:
            return rows
        for raw in reader:
            row = {k.strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
            # Map alternate column names
            mac = _normalize_mac(row.get('mac_address') or row.get('mac') or '')
            tag = (row.get('tag') or row.get('device_tag') or '').strip()
            if not mac:
                continue
            rows.append({'mac': mac, 'tag': tag})
    return rows


def sanitize_csv_rows(rows):
    """
    De-duplicate CSV rows by normalized MAC (first one wins).
    Returns (sanitized_rows, duplicate_csv_macs).
    """
    seen = set()
    sanitized = []
    duplicate_csv_macs = []
    for r in rows:
        mac = _normalize_mac(r.get('mac'))
        if not mac:
            continue
        if mac in seen:
            duplicate_csv_macs.append(mac)
            continue
        seen.add(mac)
        sanitized.append({'mac': mac, 'tag': r.get('tag', '')})
    return sanitized, sorted(set(duplicate_csv_macs))


def resolve_row(mac, new_tag, mac_to_device):
    """
    Resolve one CSV row using pre-fetched mac_to_device map (no GraphQL). Returns dict with
    mac, new_tag, device_id, current_tag, error, display fields, mac_matched.
    If MAC not in map, error='device not found'. If in map, mac_matched=True (we looked up by that MAC).
    """
    out = {
        'mac': mac,
        'new_tag': new_tag,
        'device_id': None,
        'current_tag': '',
        'error': None,
        'mac_matched': False,
        'device_name': '',
        'device_model': '',
        'device_tag': '',
        'user_id': '',
        'last_login': '',
    }
    device = mac_to_device.get(_normalize_mac(mac))
    if not device:
        out['error'] = 'device not found'
        return out
    out['device_id'] = device.get('id')
    out['current_tag'] = (_tag_display(device.get('deviceTag')))[:32]
    out['mac_matched'] = True
    info = _device_display_info(device, mac)
    out['device_name'] = info['device_name']
    out['device_model'] = info['device_model']
    out['device_tag'] = info['device_tag']
    out['user_id'] = info['user_id']
    out['last_login'] = info['last_login']
    return out


def run_updates(id_token, rows_resolved, dry_run):
    """
    For each resolved row with device_id and mac_matched, optionally perform PUT.
    Rows without matching MAC are ignored for apply. Updates rows_resolved in place.
    """
    for r in rows_resolved:
        r['updated_tag'] = None
        r['update_error'] = None
        if r.get('error') or not r.get('device_id'):
            continue
        if not r.get('mac_matched'):
            r['update_error'] = 'skipped (MAC not in device)'
            continue
        if r.get('current_tag', '') == r.get('new_tag', ''):
            r['update_error'] = 'No change'
            continue
        if dry_run:
            continue
        try:
            put_device_tag(id_token, r['device_id'], r['new_tag'])
            r['updated_tag'] = r['new_tag']
        except Exception as e:
            r['update_error'] = 'Error'
            print(f"Error updating device {r['device_id']} (MAC {r['mac']}): {e}", file=sys.stderr)


def format_table(rows_resolved, dry_run):
    """Tabular format: matched MAC, device name, model, tag, user id, last login, new tag, status."""
    cols = ['Matched MAC', 'Device Name', 'Device Model', 'Device Tag', 'User ID', 'Last Login', 'New Tag', 'Status']
    widths = [20, 16, 28, 20, 28, 22, 20, 30]
    sep = '  '
    header = sep.join(c[:w].ljust(w) for c, w in zip(cols, widths))
    lines = [header, '-' * len(header)]
    for r in rows_resolved:
        mac = (r.get('mac') or '')[:widths[0]]
        name = (r.get('device_name') or '')[:widths[1]]
        model = (r.get('device_model') or '')[:widths[2]]
        tag = (r.get('device_tag') or '')[:widths[3]]
        uid = (r.get('user_id') or '')[:widths[4]]
        login = (r.get('last_login') or '')[:widths[5]]
        new = (r.get('new_tag') or '')[:widths[6]]
        if r.get('error'):
            status = r['error']
        elif r.get('update_error'):
            status = r['update_error']
        elif r.get('updated_tag') is not None:
            status = 'Updated'
        elif r.get('mac_matched'):
            status = 'Will update'
        else:
            status = 'Skipped'
        status = status[:widths[7]]
        row = [
            mac.ljust(widths[0]), name.ljust(widths[1]), model.ljust(widths[2]),
            tag.ljust(widths[3]), uid.ljust(widths[4]), login.ljust(widths[5]),
            new.ljust(widths[6]), status.ljust(widths[7]),
        ]
        lines.append(sep.join(row))
    return '\n'.join(lines)


def main(args_dict):
    api_key = args_dict.get('apiKey') or API_KEY
    api_secret = args_dict.get('apiSecret') or API_SECRET
    env_path = args_dict.get('env_path') or ''
    if env_path:
        load_dotenv(env_path)
        api_key = os.environ.get('apiKey', api_key)
        api_secret = os.environ.get('apiSecret', api_secret)

    csv_path = args_dict['csv']
    dry_run = args_dict['dry_run']

    if not api_key or not api_secret:
        print('Missing API credentials. Use --env, --apiKey/--apiSecret, or set apiKey/apiSecret in env.', file=sys.stderr)
        sys.exit(1)

    rows = load_csv(csv_path)
    rows, duplicate_csv_macs = sanitize_csv_rows(rows)
    if not rows:
        print('No rows with MAC address found in CSV.', file=sys.stderr)
        sys.exit(1)
    if duplicate_csv_macs:
        print('Warning: duplicate MACs found in CSV after normalization (first row kept):')
        for mac in duplicate_csv_macs:
            print(f'  - {mac}')
        print()

    id_token = getToken(apiKey=api_key, apiSecret=api_secret)
    if not id_token:
        print('Failed to get token. Check API key/secret.', file=sys.stderr)
        sys.exit(1)

    client = gqlinit(id_token)

    # Single GraphQL query: fetch all devices (paginated), then filter by CSV in memory
    all_devices = fetch_all_registered_devices(client)
    mac_to_device, duplicate_backend_macs = build_mac_to_device(all_devices)
    print(f'Fetched {len(all_devices)} device(s). CSV rows: {len(rows)}.\n')

    csv_macs = {_normalize_mac(r['mac']) for r in rows}
    overlapping_dup_macs = {m for m in duplicate_backend_macs if m in csv_macs}

    if duplicate_backend_macs:
        if overlapping_dup_macs:
            print('Warning: duplicate MACs in GraphQL results OVERLAP with CSV. Apply is blocked for safety.')
        else:
            print('Warning: duplicate MACs found in GraphQL results (not in CSV, apply not affected).')
        for mac, ids in sorted(duplicate_backend_macs.items()):
            overlap = ' ** in CSV **' if mac in overlapping_dup_macs else ''
            ids_sorted = ', '.join(sorted(i for i in ids if i))
            print(f'  - {mac}: {ids_sorted}{overlap}')
        print()

    # Resolve each CSV row from the stored map (no further GraphQL)
    rows_resolved = []
    for r in rows:
        rows_resolved.append(resolve_row(r['mac'], r['tag'], mac_to_device))

    # Block apply only when duplicate backend MACs overlap with CSV
    apply_blocked = bool(overlapping_dup_macs) and not dry_run
    if apply_blocked:
        print('Apply blocked: resolve the overlapping duplicate MACs above first.\n')

    # Run updates (no-op in dry-run or when blocked)
    run_updates(id_token, rows_resolved, dry_run=(dry_run or apply_blocked))

    # One tabular output for both modes
    if dry_run or apply_blocked:
        print('Dry-run: current device info and intended new tag (no changes made)\n')
    else:
        print('Update result:\n')
    print(format_table(rows_resolved, dry_run))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Update device tags by MAC address from a CSV file (mac_address, tag).'
    )
    parser.add_argument('--env', dest='env_path', type=str, default='', help='Path to .env credential file')
    parser.add_argument('--apiKey', dest='apiKey', type=str, default=API_KEY, help='API key')
    parser.add_argument('--apiSecret', dest='apiSecret', type=str, default=API_SECRET, help='API secret')
    parser.add_argument('--csv', dest='csv', type=str, required=True, help='CSV file with mac_address and tag columns')
    parser.add_argument('--dry-run', dest='dry_run', type=booleanString, default=True, metavar='true|false', help='Only show current info and new tag; do not update (default: true). Set false to apply updates.')
    args = parser.parse_args()
    main(vars(args))
