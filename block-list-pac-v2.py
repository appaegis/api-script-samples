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

from enum import Enum
from dotenv import load_dotenv

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport


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
    r'(?:25[0-5]|2[0-4]\d|[01]?\d?\d)'
    r'(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d?\d)){3}'
)

# Regex for IPv4 subnet / CIDR
IPV4NET_REGEX = re.compile(
    r'(?:25[0-5]|2[0-4]\d|[01]?\d?\d)'
    r'(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d?\d)){3}/'
    r'(?:[0-9]|[12]\d|3[0-2])'
)

class entrytype(Enum):
    Unknown = 0
    IPv4 = 1
    CIDR = 2
    Domain = 3

def get_ipblocklist(blocklist):
    return ",".join(f'"{s}"' for s in blocklist)

def get_pacfile(ipblocklist):
  return f"""
    var BLOCKED_IPS = [
    {ipblocklist}
    ];

    var BLOCKED_DICT = {{}};
    for (var i = 0; i < BLOCKED_IPS.length; i++) {{
        BLOCKED_DICT[BLOCKED_IPS[i]] = true;
    }}

    // Define the blackhole proxy — a non-routable or invalid proxy to cause connection failure.
    var BLOCK_PROXY = "PROXY 127.0.0.1:9999";
    var DIRECT = "DIRECT";

    function FindProxyForURL(url, host) {{
        // 1) Resolve host to IP
        var ip = dnsResolve(host);
        if (ip == null) {{
            // Could not resolve, fallback to direct or block, depending on your policy
            return DIRECT;
        }}

        // 2) Check if IP is in the blocked list
        if (BLOCKED_DICT[ip] === true) {{
            // Return the blackhole proxy => effectively blocks the request
            return BLOCK_PROXY;
        }}

        // 3) If not blocked, allow direct
        return DIRECT;
    }}
  """


def gqlinit(idToken):
  transport = AIOHTTPTransport(url=f'{API_HOST}/graphql', headers={'Authorization': f'Bearer {idToken}'})
  client = Client(transport=transport, fetch_schema_from_transport=False)
  return client

def gqlexec(client, query, variables):
  result = client.execute(query, variable_values=variables)
  return result

def block_entry_type(candidate: str) -> entrytype: 
  # is it IPv4 addresses
  try:
    ipaddress.ip_address(candidate)
    return entrytype.IPv4
  except ValueError:
    pass

  # is it v4 subnet
  try:
    # Use IPv4Network. `strict=False` allows host bits to be set (e.g., "192.168.0.1/24")
    ipaddress.IPv4Network(candidate, strict=False)
    return entrytype.CIDR
  except ValueError:
    pass

  # is it domains
  if DOMAIN_REGEX.match(candidate) or WILDCARD_DOMAIN_REGEX.match(candidate):
     return entrytype.Domain

  return entrytype.Unknown

def get_longest_match_in_line(line: str) -> str:
    """
    Searches the line for any standard domain, wildcard domain, or IPv4 address.
    Returns the longest match found, or None if there are no matches.
    """
    all_matches = []

    # Find all domain matches
    all_matches.extend(m.group(0) for m in DOMAIN_REGEX.finditer(line))
    
    # Find all wildcard domain matches
    all_matches.extend(m.group(0) for m in WILDCARD_DOMAIN_REGEX.finditer(line))

    # Find all IPv4 address matches
    all_matches.extend(m.group(0) for m in IPV4_REGEX.finditer(line))

    # Find all IPv4 subnet matches
    all_matches.extend(m.group(0) for m in IPV4NET_REGEX.finditer(line))

    if not all_matches:
        return None

    # Pick the longest matched string by character length
    return max(all_matches, key=len)

def read_domains_and_extract_longest(filepath: str, url: str) -> list:
    """
    This is the main parsing function.
    Reads each line from the given file, skipping empty lines and lines that start
    with '#', extracts the longest valid domain match if present, and returns 
    a list of those matches (or None for lines with no match).
    """
    lines_total =0
    lines_skipped = 0
    lines_parsed = 0
    lines_failed = 0
    count_domain = 0
    count_ipv4 = 0
    count_cidr = 0
    results = []

    print()
    print("Parsing:")

    # open input stream from file or url
    stream = open(filepath, 'r') if len(filepath)>0 else urllib.request.urlopen(url)
    with stream:
        for rawline in stream:
            lines_total += 1

            if isinstance(rawline, bytes):
               rawline = rawline.decode("utf-8")
               
            line = rawline.strip()
            # Skip empty lines or lines starting with '#' or '!'
            if not line or line.startswith('#') or line.startswith('!'):
                lines_skipped += 1
                continue

            longest_match = get_longest_match_in_line(line)
            if not longest_match or longest_match.strip() == '':
                print(f"Failed to parse: {line}")
                lines_failed += 1
                continue

            candidate = longest_match.strip()
            lines_parsed += 1

            ### Now check the type
            type = block_entry_type(candidate)
            if type == entrytype.CIDR:
              count_cidr += 1
            elif type == entrytype.IPv4:
              count_ipv4 += 1
              results.append(candidate)
            elif type == entrytype.Domain:
               count_domain += 1

            # now add this new result

    print(f"Total   lines: {lines_total}")
    print(f"Skipped lines: {lines_skipped}")
    print(f"Success lines: {lines_parsed}")
    print(f"Failed  lines: {lines_failed}")
    print(f"   IPv4 addrs: {count_ipv4}")
    print(f"   IPv4subnet: {count_cidr}")
    print(f"      Domains: {count_domain}")
    print()
    return results

def update_blocklist(client: Client, blocklist: list):
  # query web category
  query = gql(
    """
      query ListUnityDefaultForwardingPolicys {
        listUnityDefaultForwardingPolicys {
          items {
            id
            defaultForwardingAction {
                actionType
                targetURL
                pacContent
            }
          }
        }
      }
    """
  )
  # query the pre-defined block category
  result = gqlexec(client, query, None)
  defpolicy_list = result['listUnityDefaultForwardingPolicys']
  defpolicy = defpolicy_list['items'][0]

  print(f"Old def policy: {defpolicy}")

  defpolicy['defaultForwardingAction']['actionType'] = "pac"
  defpolicy['defaultForwardingAction']['targetURL'] = None
  defpolicy['defaultForwardingAction']['pacContent'] = get_pacfile(get_ipblocklist(blocklist))

  # write back the changed object and check the new value
  update = gql(
    """
      mutation UpdateUnityDefaultForwardingPolicy(
              $input: UpdateUnityDefaultForwardingPolicyInput!
            ) {
              updateUnityDefaultForwardingPolicy(input: $input) {
                id
                defaultForwardingAction {
                  actionType
                  targetURL
                  pacContent
                }
              }
            }
    """
  )
  variables = { "input": defpolicy }
  result = gqlexec(client, update, variables)
  new_defpolicy = result['updateUnityDefaultForwardingPolicy']

  # verify that the updated block list is the same as the one we set
  print(f"Update result matches: {new_defpolicy == new_defpolicy}")
  # If you want to see the updated object, uncomment the line below
  # result_string = json.dumps(new_webcat, indent=4)
  # print(result_string)


def main(argsdict):
  # The order to searching for API key: 
  #   environment variables, 
  #   the --apiKey command line argument, 
  #   the --env argument.
  # if more than one is provided, the later option will override option checked earlier.
  apiKey = argsdict['apiKey']
  apiSecret = argsdict['apiSecret']
  env_path = argsdict['env_path']
  if env_path and env_path != '':
    load_dotenv(env_path)
    apiKey = os.environ.get('apiKey', apiKey)
    apiSecret = os.environ.get('apiSecret', apiSecret)

  # parse input file
  blocklist = read_domains_and_extract_longest(argsdict['file'], argsdict['url'])

  # acquire auth token
  idToken = getToken(apiKey=apiKey, apiSecret=apiSecret)
  # init GraphQL client
  client = gqlinit(idToken)

  # take action
  # note we have size limit of up to 5000
  update_blocklist(client, blocklist[:5000])
  return

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Change the default block list')
  parser.add_argument('--env', dest='env_path', type=str, default='', required=False, help='Path to the credential file in dotenv format')
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument('--file', dest='file', type=str, default='', help='Path to the file containing the block list')
  group.add_argument('--url',  dest='url',  type=str, default='', help='HTTP/HTTPS URL to the block list')
  parser.add_argument('--apiKey', dest='apiKey', type=str, default=API_KEY, required=False, help='API key if not set in environment')
  parser.add_argument('--apiSecret', dest='apiSecret', type=str, default=API_SECRET, required=False, help='API secret if not set in environment')
  args = parser.parse_args()

  main(vars(args))
