#!/usr/bin/env python
# coding: utf-8


from lib.common import API_KEY
from lib.common import API_SECRET
from lib.common import API_HOST

from lib.common import getToken
from lib.common import booleanString

import ipaddress
import logging
import argparse
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

def read_domains_and_extract_longest(filepath: str) -> list:
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

    with open(filepath, 'r', encoding='utf-8') as file:
        for line in file:
            lines_total += 1
            line = line.strip()

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
            elif type == entrytype.Domain:
               count_domain += 1

            # now add this new result
            results.append(candidate)

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
      fragment WebCategoryFields on WebCategory {
        id
        name
        description
        usage
        dynamicURLCategories
        preDefinedVariant
        excludeList
        includeList
      }

      query ListWebCategorys( $namefilter: String! ) {
        listWebCategorys (filter: { name: { eq: $namefilter } }) {
          items {
            ...WebCategoryFields
          }
          total
        }
      }
    """
  )
  # query the pre-defined block category
  variables = { "namefilter": "Advanced Safe Browsing" }
  result = gqlexec(client, query, variables)
  webcat_list = result['listWebCategorys']
  blockcat = webcat_list['items'][0]

  # modify the include list of this block category
  # Add static entries like below
  # blocklist.append("3.4.5.6")
  blockcat['includeList'] = blocklist
  print(f"new block list size: {len(blocklist)}")

  # write back the changed object and check the new value
  update = gql(
    """
      fragment WebCategoryFields on WebCategory {
        id
        name
        description
        usage
        dynamicURLCategories
        preDefinedVariant
        excludeList
        includeList
      }

      mutation UpdateWebCategory($input: UpdateWebCategoryInput!) {
        updateWebCategory(input: $input) {
            ...WebCategoryFields
        }
      }
    """
  )
  variables = { "input": blockcat }
  result = gqlexec(client, update, variables)
  new_webcat = result['updateWebCategory']

  # verify that the updated block list is the same as the one we set
  newblocklist = new_webcat['includeList']
  print(f"Update result matches: {newblocklist == blocklist}")
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
  file_path = argsdict['file']
  blocklist = read_domains_and_extract_longest(file_path)

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
  parser.add_argument('--file', dest='file', type=str, default='', required=True, help='Path to the file containing the block list')
  parser.add_argument('--apiKey', dest='apiKey', type=str, default=API_KEY, required=False, help='API key if not set in environment')
  parser.add_argument('--apiSecret', dest='apiSecret', type=str, default=API_SECRET, required=False, help='API secret if not set in environment')
  args = parser.parse_args()

  main(vars(args))
