# coding: utf-8

import os
import json
import argparse
import logging

import requests


API_HOST = os.getenv('API_HOST')
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

def booleanString(s):
    if s.lower() not in {'false', 'true', 't', 'f', 'yes', 'no', 'y', 'n'}:
        raise ValueError('Not a valid boolean string')
    return s.lower() in {'true', 't', 'yes', 'y'}

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
