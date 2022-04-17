# coding: utf-8

import os
import json
import logging
import urllib

import requests
import pydash

API_HOST = os.getenv('API_HOST', 'https://api.appaegis.net')
USER_EMAIL = os.getenv('USER_EMAIL')
USER_SSH_IP = os.getenv('USER_SSH_IP')
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')

TOKEN_EXCHANGE = '/api/v1/authentication'
USER_API = '/api/v1/users'
TEAM_API = '/api/v1/teams'
ROLE_API = '/api/v1/accessRoles'
POLICY_API = '/api/v1/policies'
APP_API = '/api/v1/applications'
LOOK_UP_IDS_API = '/api/v1/util/lookupIds'

NETWORKS_API = '/api/v1/networks'

def booleanString(s):
  if s.lower() not in {'false', 'true', 't', 'f', 'yes', 'no', 'y', 'n'}:
      raise ValueError('Not a valid boolean string')
  return s.lower() in {'true', 't', 'yes', 'y'}

def argString(s):
  return str(s)

def getToken(apiKey, apiSecret):
  payload = {
    'apiSecret': apiSecret,
    'apiKey': apiKey,
  }
  resp = requests.post(
    f'{API_HOST}{TOKEN_EXCHANGE}',
    data=json.dumps(payload),
    headers={'content-type': 'application/json'})
  output = resp.json()
  return output.get('Authorization', None)


def getResource(id, idToken, url):
  logging.debug(f'Read by id: {url}, {id}')
  quotedId = urllib.parse.quote(id)
  url = f'{url}/{quotedId}'
  resp = requests.get(
    f'{API_HOST}{url}',
    headers={'content-type': 'application/json', 'idToken': idToken})
  output = resp.json()
  error = pydash.get(output, 'error', None)
  if resp.status_code >= 400 or error != None:
    raise Exception(output)
  return output

def getResources(idToken, url):
  logging.debug(f'Read all: {url}')
  resp = requests.get(
    f'{API_HOST}{url}',
    headers={'content-type': 'application/json', 'idToken': idToken})
  output = resp.json()
  return output
