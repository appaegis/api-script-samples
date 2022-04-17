# coding: utf-8

import json
import urllib
import logging

import requests
import pydash

from .common import API_HOST


def updateResource(dryrun, id, idToken, url, data = None):
  logging.debug(f'Update: {url}, id: {id}, data: {data}')
  kwargs = {}
  if data != None:
    data.pop('id')
    pydash.set_(kwargs, 'data', json.dumps(data))

  # print for dry run
  if dryrun == True:
    if bool(kwargs):
      logging.warning(f'Update: {url.split("/v1/",2)[1]}: item: {kwargs}')
    else:
      logging.warning(f'Update: {url.split("/v1/",2)[1]}: {id}')
    return ''

  quotedId = urllib.parse.quote(id)
  url = f'{url}/{quotedId}'
  resp = requests.put(
    f'{API_HOST}{url}',
    headers={'content-type': 'application/json', 'idToken': idToken},
    **kwargs,
  )
  output = resp.status_code
  return output

def purgeResource(dryrun, id, idToken, url, data = None):
  logging.debug(f'Remove: {url}, id: {id}, data: {data}')
  kwargs = {}
  if data != None:
    pydash.set_(kwargs, 'data', json.dumps(data))

  # print for dry run
  if dryrun == True:
    if bool(kwargs):
      logging.warning(f'Remove: {url.split("/v1/",2)[1]}: item: {kwargs}')
    else:
      logging.warning(f'Delete: {url.split("/v1/",2)[1]}: {id}')
    return ''

  quotedId = urllib.parse.quote(id)
  url = f'{url}/{quotedId}'
  resp = requests.delete(
    f'{API_HOST}{url}',
    headers={'content-type': 'application/json', 'idToken': idToken},
    **kwargs,
  )
  output = resp.status_code
  return output
