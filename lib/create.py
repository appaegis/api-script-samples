# coding: utf-8

import json
import logging

import requests
import pydash

from .common import API_HOST


def createResource(idToken, url, data = None):
  kwargs = {}
  if data != None:
    pydash.set_(kwargs, 'data', json.dumps(data))
  resp = requests.post(
    f'{API_HOST}{url}',
    headers={'content-type': 'application/json', 'idToken': idToken},
    **kwargs,
  )
  output = resp.json()
  # NOTE: not allow resource creating only with out new user entry
  error = pydash.get(output, 'error', None)
  if resp.status_code >= 400 or error != None:
    logging.error(output)
    raise Exception(output)
  return output
