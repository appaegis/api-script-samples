#!/usr/bin/env python
# coding: utf-8

import logging
import argparse
import pprint

from lib.common import API_KEY
from lib.common import API_SECRET

from lib.common import NETWORKS_API

from lib.common import booleanString
from lib.common import argString

from lib.common import getToken
from lib.common import getResources
from lib.common import getResource


def main(argsdict):
  debug = argsdict.get('debug')
  nwname = argsdict.get('nwname')
  if debug:
    logging.getLogger().setLevel(logging.DEBUG)

  idToken = getToken(apiSecret=API_SECRET, apiKey=API_KEY)
  networks = getResources(
    idToken=idToken,
    url=NETWORKS_API,
  )

  if not bool(nwname):
    pprint.pprint(networks)
  else:
    for nw in networks:
      if str(nw.get('name')) == nwname:
        nw = getResource(
          id=nw['id'],
          idToken=idToken,
          url=NETWORKS_API,
        )
        pprint.pprint(nw)



if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Add new user and associated objects')
  parser.add_argument('--debug', dest='debug', type=booleanString, default=False,
                      required=False, help='Output verbose log')
  parser.add_argument('--nwname', dest='nwname', type=argString, default=False,
                      required=False, help='Output verbose log')
  args = parser.parse_args()
  main(vars(args))
