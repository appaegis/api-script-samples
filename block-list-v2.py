#!/usr/bin/env python
# coding: utf-8

from lib.common import API_KEY
from lib.common import API_SECRET
from lib.common import API_HOST
from lib.common import getToken
from lib.common import booleanString

import ipaddress
import argparse
import urllib
import json
import os
import re
import requests

from enum import Enum
from dotenv import load_dotenv

# Regex for standard domain: "example.com" or "sub-domain.co.uk"
DOMAIN_REGEX = re.compile(
    r'([A-Za-z0-9-]+\.)+([A-Za-z]{2,})+'
)

# Regex for wildcard domain: "*.example.com"
WILDCARD_DOMAIN_REGEX = re.compile(
    r'\*\.([A-Za-z0-9-]+\.)*([A-Za-z]{2,})+'
)

# Regex for IPv4 addresses: "192.168.0.1", "255.255.255.255", etc.
IPV4_REGEX = re.compile(
    r'^(?:25[0-5]|2[0-4]\d|[01]?\d?\d)'
    r'(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d?\d)){3}$'
)

# Regex for IPv4 subnet / CIDR
IPV4NET_REGEX = re.compile(
    r'^(?:25[0-5]|2[0-4]\d|[01]?\d?\d)'
    r'(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d?\d)){3}/'
    r'(?:3[0-2]|[12]\d|\d)$'
)

class entrytype(Enum):
    Unknown = 0
    IPv4 = 1
    CIDR = 2
    Domain = 3


def is_invalid_ip_format(candidate: str) -> bool:
    """Check if this looks like an IP but is actually invalid"""
    # Check for patterns like 33.33.33.333 (invalid octets)
    parts = candidate.split('.')
    if len(parts) == 4:
        try:
            for part in parts:
                num = int(part)
                if num > 255:  # Invalid octet
                    return True
        except ValueError:
            pass
    return False

def is_invalid_cidr(candidate: str) -> bool:
    """Check if this looks like a CIDR but is actually invalid"""
    # Check if it looks like IP/number format but is invalid
    parts = candidate.split('/')
    if len(parts) == 2:
        ip_part, cidr_part = parts
        # Check if IP part looks valid but CIDR part is invalid
        try:
            ipaddress.ip_address(ip_part)
            cidr_num = int(cidr_part)
            if cidr_num > 32:  # Invalid CIDR for IPv4
                return True
        except ValueError:
            pass
    return False

def block_entry_type(candidate: str) -> entrytype:
    # Check for invalid formats first (to avoid treating them as other types)
    if is_invalid_cidr(candidate) or is_invalid_ip_format(candidate):
        return entrytype.Unknown

    # is it IPv4 addresses
    try:
        ipaddress.ip_address(candidate)
        return entrytype.IPv4
    except ValueError:
        pass

    # is it v4 subnet (use regex for strict validation)
    if IPV4NET_REGEX.fullmatch(candidate):
        return entrytype.CIDR

    # is it domains
    if DOMAIN_REGEX.match(candidate) or WILDCARD_DOMAIN_REGEX.match(candidate):
        return entrytype.Domain

    return entrytype.Unknown

def get_longest_match_in_line(line: str) -> str:
    """
    Searches the line for any standard domain, wildcard domain, or IPv4 address.
    Returns the longest match found, or None if there are no matches.
    """
    stripped_line = line.strip()
    all_matches = []

    # Check for valid CIDR first (complete line match)
    if IPV4NET_REGEX.fullmatch(stripped_line):
        return stripped_line

    # Check if it's an invalid CIDR format (IP/number but invalid)
    if is_invalid_cidr(stripped_line):
        return stripped_line  # Return it so we can process and warn about it

    # Check if it's an invalid IP format (like 33.33.33.333)
    if is_invalid_ip_format(stripped_line):
        return stripped_line  # Return it so we can process and warn about it

    # Check for complete IPv4 address (must match entire line)
    if IPV4_REGEX.fullmatch(stripped_line):
        return stripped_line

    # Find domain matches within the line
    all_matches.extend(m.group(0) for m in DOMAIN_REGEX.finditer(stripped_line))
    all_matches.extend(m.group(0) for m in WILDCARD_DOMAIN_REGEX.finditer(stripped_line))

    if not all_matches:
        return None
    return max(all_matches, key=len)

def read_domains_and_extract_longest(filepath: str, url: str) -> list:
    """
    Reads each line from the given file, skipping empty lines and lines that start
    with '#' or '!', extracts the longest valid domain match if present, and returns
    a list of those matches (or None for lines with no match).
    """
    lines_total = 0
    lines_skipped = 0
    lines_parsed = 0
    lines_failed = 0
    lines_invalid = 0
    count_domain = 0
    count_ipv4 = 0
    count_cidr = 0
    results = []
    invalid_entries = []

    print()
    print("Parsing:")
    stream = open(filepath, 'r') if len(filepath) > 0 else urllib.request.urlopen(url)
    with stream:
        for rawline in stream:
            lines_total += 1
            if isinstance(rawline, bytes):
                rawline = rawline.decode("utf-8")
            line = rawline.strip()
            if not line or line.startswith('#') or line.startswith('!'):
                lines_skipped += 1
                continue

            longest_match = get_longest_match_in_line(line)
            if not longest_match or longest_match.strip() == '':
                print(f"Failed to parse: {line}")
                lines_failed += 1
                continue

            candidate = longest_match.strip()
            type = block_entry_type(candidate)

            if type == entrytype.Unknown:
                # Check what type of invalid format it is
                if is_invalid_cidr(candidate):
                    print(f"⚠️  Invalid CIDR (ignored): {candidate}")
                    invalid_entries.append(f"Invalid CIDR: {candidate}")
                    lines_invalid += 1
                elif is_invalid_ip_format(candidate):
                    print(f"⚠️  Invalid IP (ignored): {candidate}")
                    invalid_entries.append(f"Invalid IP: {candidate}")
                    lines_invalid += 1
                else:
                    print(f"⚠️  Unknown format (ignored): {candidate}")
                    invalid_entries.append(f"Unknown format: {candidate}")
                    lines_invalid += 1
                continue

            # Valid entry
            lines_parsed += 1
            if type == entrytype.CIDR:
                count_cidr += 1
            elif type == entrytype.IPv4:
                count_ipv4 += 1
            elif type == entrytype.Domain:
                count_domain += 1

            results.append(candidate)
    print("Done.")

    # Summary
    print()
    print(f"Total   lines: {lines_total}")
    print(f"Skipped lines: {lines_skipped} (comments/empty)")
    print(f"Success lines: {lines_parsed} (valid entries)")
    print(f"Failed  lines: {lines_failed} (unparseable)")
    print(f"Invalid lines: {lines_invalid} (recognized but invalid)")
    print(f"")
    print(f"Valid entries breakdown:")
    print(f"   IPv4 addrs: {count_ipv4}")
    print(f"   IPv4subnet: {count_cidr}")
    print(f"      Domains: {count_domain}")
    print(f"   Total valid: {lines_parsed}")

    # Show invalid entries if any
    if invalid_entries:
        print()
        print("⚠️  WARNING: The following entries were ignored due to invalid format:")
        for i, entry in enumerate(invalid_entries, 1):
            print(f"   {i}. {entry}")
        print("   Please check these entries and correct them if needed.")

    print()
    return results

def update_blocklist_rest(idToken: str, blocklist: list):
    # Use REST API to update blocked sites
    url = f"{API_HOST}/api/v2/blocked-sites"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': idToken
    }
    data = {
        'sites': blocklist
    }
    response = requests.put(url, headers=headers, data=json.dumps(data))
    if response.status_code >= 400:
        print(f"Failed to update blocklist: {response.status_code} {response.text}")
        return False
    print(f"Blocklist updated successfully.")
    return True

def main(argsdict):
    apiKey = argsdict['apiKey']
    apiSecret = argsdict['apiSecret']
    env_path = argsdict['env_path']
    if env_path and env_path != '':
        load_dotenv(env_path)
        apiKey = os.environ.get('apiKey', apiKey)
        apiSecret = os.environ.get('apiSecret', apiSecret)
    blocklist = read_domains_and_extract_longest(argsdict['file'], argsdict['url'])

    idToken = getToken(apiKey=apiKey, apiSecret=apiSecret)
    if not idToken:
        print("Failed to get idToken. Please check your API key/secret.")
        return
    update_blocklist_rest(idToken, blocklist)
    return

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Change the default block list using REST API')
    parser.add_argument('--env', dest='env_path', type=str, default='', required=False, help='Path to the credential file in dotenv format')
    parser.add_argument('--apiKey', dest='apiKey', type=str, default=API_KEY, required=False, help='API key if not set in environment')
    parser.add_argument('--apiSecret', dest='apiSecret', type=str, default=API_SECRET, required=False, help='API secret if not set in environment')
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--file', dest='file', type=str, default='', help='Path to the file containing the block list')
    input_group.add_argument('--url',  dest='url',  type=str, default='', help='HTTP/HTTPS URL to the block list')
    args = parser.parse_args()
    main(vars(args))
