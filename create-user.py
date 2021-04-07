#!/usr/bin/env python
# coding: utf-8

import logging
import argparse

from lib.common import USER_EMAIL
from lib.common import API_KEY
from lib.common import API_SECRET
from lib.common import USER_SSH_IP
from lib.common import USER_API
from lib.common import TEAM_API
from lib.common import ROLE_API
from lib.common import POLICY_API
from lib.common import APP_API

from lib.common import getToken
from lib.common import booleanString
from lib.create import createResource


def main(argsdict):
  debug = argsdict.get('debug')
  if debug:
    logging.getLogger().setLevel(logging.DEBUG)
  name = USER_EMAIL.split('@')[0]
  email = USER_EMAIL
  host = USER_SSH_IP.split(':')[0]
  port = int(USER_SSH_IP.split(':')[1])
  idToken = getToken(apiSecret=API_SECRET, apiKey=API_KEY)
  logging.warning(f'Add user: {email}')

  user = createResource(
    idToken=idToken,
    url=USER_API,
    data={
      'suspended': False,
      'name': name,
      'teamIds': [],
      'adminRole': 'user',
      'mfa': False,
      'accessRoleIds': [],
      'email': email
    },
  )
  team = createResource(
    idToken=idToken,
    url=TEAM_API,
    data={
      'name': name,
      'emails': [
        email,
      ],
      'accessRoleIds': [
      ]
    },
  )
  teamId = team.get('id')
  role = createResource(
    idToken=idToken,
    url=ROLE_API,
    data={
      'name': name,
      'emails': [
        email,
      ],
      'teamIds': [
        teamId,
      ]
    },
  )
  roleId = role.get('id')
  policy = createResource(
    idToken=idToken,
    url=POLICY_API,
    data={
      'name': name,
      'rules': [
        {
          'accessRoleIds': [
            roleId
          ],
          'actions': [
            'copy',
            'paste',
          ]
        },
      ]
    },
  )
  policyId = policy.get('id')
  app = createResource(
    idToken=idToken,
    url=APP_API,
    data={
      'name': name,
      'type': 'saas',
      'policyId': policyId,
      'isolation': True,
      'iconUrl': None,
      'protocol': 'ssh',
      'host': [host],
      'port': port,
    },
  )
  appId = app.get('id')

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Add new user and associated objects')
  parser.add_argument('--debug', dest='debug', type=booleanString, default=False,
                      required=False, help='Output verbose log')
  args = parser.parse_args()
  main(vars(args))
