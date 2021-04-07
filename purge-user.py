#!/usr/bin/env python
# coding: utf-8

import logging
import argparse

import pydash

from lib.common import USER_EMAIL
from lib.common import API_KEY
from lib.common import API_SECRET
from lib.common import USER_API
from lib.common import TEAM_API
from lib.common import ROLE_API
from lib.common import POLICY_API
from lib.common import APP_API

from lib.common import getToken
from lib.common import booleanString
from lib.purge import getResource
from lib.purge import getResources
from lib.purge import updateResource
from lib.purge import purgeResource


def main(argsdict):
  dryrun = argsdict.get('dryrun')
  debug = argsdict.get('debug')
  if debug:
    logging.getLogger().setLevel(logging.DEBUG)
  userId = USER_EMAIL
  logging.warning(f'Remove user: {userId}, Dryrun: {dryrun}')
  idToken = getToken(apiSecret=API_SECRET, apiKey=API_KEY)
  user = getResource(id=userId, idToken=idToken, url=USER_API)

  # TODO: check the team contains only this user
  #       also need to skip "groups"
  teamIds = user.get('teamIds', [])
  accessRoleIds = user.get('accessRoleIds')

  # NOTE: Fetch all apps and related policyId
  policyAppMapper = {}
  apps = getResources(idToken=idToken, url=APP_API)
  for app in apps:
    appId = app.get('id')
    policyId = app.get('policyId')
    # policy exists
    if bool(policyId):
      appIds = pydash.get(policyAppMapper, f'{policyId}.appId', [])
      appIds.append(appId)
      pydash.set_(policyAppMapper, f'{policyId}.appId', appIds)

  # NOTE: Check each policy if it's deletable or not. It only handles ruleRoleLink except Role
  policyIds = list(policyAppMapper.keys())
  for policyId in policyIds:
    policyRoleIds = []
    policy = getResource(id=policyId, idToken=idToken, url=POLICY_API)
    rules = pydash.objects.get(policy, 'rules')
    for rule in rules:
      roleIds = pydash.objects.get(rule, 'accessRoleIds')
      policyRoleIds.append(roleIds)
    policyRoleIds = pydash.flatten_deep(policyRoleIds)
    # NOTE: In case the policyRoleIds is totally equal with userRoleIds, we will delete it.
    if set(policyRoleIds) <= set(accessRoleIds):
      pydash.set_(policyAppMapper, f'{policyId}.deletable', True)
    else:
      pydash.set_(policyAppMapper, f'{policyId}.deletable', False)

  deletablePolicyMapper = pydash.pick_by(policyAppMapper, lambda item: pydash.get(item, 'deletable') == True)
  deletablePolicyIds = list(deletablePolicyMapper.keys())
  deletableAppIds = pydash.flatten_deep([pydash.get(deletablePolicyMapper, f'{i}.appId') for i in deletablePolicyMapper])

  # NOTE: delete app if its policy will be deleted.
  for appId in deletableAppIds:
    purgeResource(dryrun, id=appId, idToken=idToken, url=APP_API)

  # NOTE: delete policy something like policyEntry, policyRole relationship and ruleEntry
  for policyId in deletablePolicyIds:
    purgeResource(dryrun, id=policyId, idToken=idToken, url=POLICY_API)
  
  # NOTE: remove relationship something like userTeamLink, userRoleLink, teamRoleLink.
  for teamId in teamIds:
    purgeResource(dryrun, id=teamId, idToken=idToken, url=f'{TEAM_API}/{teamId}/users/', data=[userId])
  for roleId in accessRoleIds:
    purgeResource(dryrun, id=roleId, idToken=idToken, url=f'{ROLE_API}/{roleId}/users/', data=[userId])
    purgeResource(dryrun, id=roleId, idToken=idToken, url=f'{ROLE_API}/{roleId}/teams/', data=teamIds)

  # NOTE: remove teams
  deletableTeamIds = []
  for teamId in teamIds:
    team = getResource(id=teamId, idToken=idToken, url=TEAM_API)
    teamEmails = pydash.get(team, 'emails')
    teamRoleIds = pydash.get(team, 'accessRoleIds')
    # NOTE: check the role contains only this user and teams
    if len(set(teamEmails) - set([userId])) == 0 and len(set(teamRoleIds) - set(accessRoleIds)) == 0:
      deletableTeamIds.append(teamId)

  # NOTE: remove roles
  deletableRoleIds = []
  for roleId in accessRoleIds:
    role = getResource(id=roleId, idToken=idToken, url=ROLE_API)
    roleEmails = pydash.get(role, 'emails')
    roleTeamIds = pydash.get(role, 'teamIds')
    # NOTE: check the role contains only this user and teams
    if len(set(roleEmails) - set([userId])) == 0 and len(set(roleTeamIds) - set(teamIds)) == 0:
      deletableRoleIds.append(roleId)

  for teamId in deletableTeamIds:
    purgeResource(dryrun, id=teamId, idToken=idToken, url=TEAM_API)
  for roleId in deletableRoleIds:
    purgeResource(dryrun, id=roleId, idToken=idToken, url=ROLE_API)

  # NOTE: handle orphan policy once app was deleted before
  updatablePolicyDataSet = {}
  deletablePolicyIds = {}
  policies = getResources(idToken=idToken, url=POLICY_API)
  for policy in policies:
    policyId = policy.get('id')
    policyRoleIds = []
    rules = pydash.objects.get(policy, 'rules')
    for ruleIdx, rule in enumerate(rules):
      ruleRoleIds = rule.get('accessRoleIds')
      policyRoleIds.append(ruleRoleIds)

      # NOTE: Handle the detail Configure policy
      remainingRuleRoleIds = set(ruleRoleIds) - set(accessRoleIds)
      remainingRuleRoleIds = list(remainingRuleRoleIds)
      if len(remainingRuleRoleIds) > 0 and len(ruleRoleIds) != len(remainingRuleRoleIds):
        newPolicy = pydash.get(updatablePolicyDataSet, policyId, pydash.clone_deep(policy))
        pydash.set_(newPolicy, f'rules.{ruleIdx}.accessRoleIds', remainingRuleRoleIds)
        pydash.set_(updatablePolicyDataSet, policyId, newPolicy)
      elif len(remainingRuleRoleIds) == 0:
        newPolicy = pydash.get(updatablePolicyDataSet, policyId, pydash.clone_deep(policy))
        pydash.set_(newPolicy, f'rules.{ruleIdx}.accessRoleIds', [])
        pydash.set_(updatablePolicyDataSet, policyId, newPolicy)

    policyRoleIds = pydash.flatten_deep(policyRoleIds)
    # NOTE: In case the policyRoleIds is totally equal with userRoleIds, we will delete it.
    if set(policyRoleIds) <= set(accessRoleIds):
      pydash.set_(deletablePolicyIds, policyId, policy)
    elif len(policyRoleIds) == 0:
      # NOTE: Relationship was removed previously
      pydash.set_(deletablePolicyIds, policyId, policy)

  # NOTE: Handle Configure policy
  for policyId in updatablePolicyDataSet:
    policy = pydash.get(updatablePolicyDataSet, policyId)
    if pydash.get(deletablePolicyIds, policyId, None) != None:
      continue
    rules = policy.get('rules', [])
    newRules = [rule for rule in rules if len(rule.get('accessRoleIds', [])) > 0]
    pydash.set_(policy, 'rules', newRules)
    updateResource(dryrun, id=policyId, idToken=idToken, url=POLICY_API, data = policy)

  for policyId in deletablePolicyIds:
    purgeResource(dryrun, id=policyId, idToken=idToken, url=POLICY_API)

  # NOTE: handle orphan team once app was deleted before
  orphanTeamIds = []
  teams = getResources(idToken=idToken, url=TEAM_API)
  for team in teams:
    teamId = team.get('id')
    teamEmails = pydash.get(team, 'emails')
    if teamEmails == [userId]:
      # NOTE: Other case will be hanlded by user deleting
      orphanTeamIds.append(teamId)
  for teamId in orphanTeamIds:
    purgeResource(dryrun, id=teamId, idToken=idToken, url=f'{TEAM_API}/{teamId}/users/', data=[userId])

  # NOTE: handle orphan role once app was deleted before
  orphanRoleIds = []
  roles = getResources(idToken=idToken, url=ROLE_API)
  for role in roles:
    roleId = role.get('id')
    roleEmails = pydash.get(role, 'emails')
    roleTeamIds = pydash.get(role, 'teamIds')
    # NOTE: skip this team including others relationship
    if roleEmails == [userId] and len(set(roleTeamIds) - set(teamIds)) == 0:
      orphanRoleIds.append(roleId)
  for roleId in orphanRoleIds:
    purgeResource(dryrun, id=roleId, idToken=idToken, url=ROLE_API)

  # NOTE: remove userEntry, and his relationship team, rule link, etc
  # TODO: check the team contains only this user
  #       also need to skip "groups"
  purgeResource(dryrun, id=userId, idToken=idToken,  url=USER_API)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Remove existing user and associated objects')
  parser.add_argument('--dryrun', dest='dryrun', type=booleanString, default=True,
                      required=True, help='In dryrun mode, no objects will be deleted')
  parser.add_argument('--debug', dest='debug', type=booleanString, default=False,
                      required=False, help='Output verbose log')

  args = parser.parse_args()
  main(vars(args))
