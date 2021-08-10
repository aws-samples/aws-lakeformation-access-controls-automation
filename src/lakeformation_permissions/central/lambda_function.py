# Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import boto3
import logging
import os
from botocore.config import Config


logger = logging.getLogger()
logger.setLevel(logging.INFO)




class Error(Exception):
    """Base class for other exceptions"""
    pass

class LFAttributeError(Error):
    """Raised when one or more mandatory Lake Formation Permission Perameters are Missing"""
    pass    
def grant_db_describe(principal, database):

    """  Grants 'DESCRIBE' on database to the Principal 
    Arguments: 
        principal {str} -- Principal to which DB describe is needed
        database  {str} -- Database Name   
    
    Returns:
        response {dict} -- response from Lakeformation API call
    """    

    Name = database
    permissions = ['DESCRIBE'] 
    database_json = {}

    Database = {
        'Name': database
    }
    database_json['Database'] = Database
    client = boto3.client('lakeformation', config=Config(connect_timeout=5, read_timeout=60, retries={'max_attempts': 20}))
    logger.info('Granting DB Describe on resource {} for Principal {}'
                        .format(principal, database ))
    response= client.grant_permissions(Principal=principal,
                            Resource=database_json,
                            Permissions=permissions)
    logger.info('DB DESCRIBE Grant Response {}'.format(response))
    return response 

def buildjson(event):

    """  builds the json event consumed by Lakeformation API 
    Arguments:  
        event {dict} -- event that is pushed to account specific queue
    
    Returns:
        principal_json {dict}         --   (sample event below)
                                    Principal={
                                            'DataLakePrincipalIdentifier': 'string'
                                        }
        table_json {dict}             --   (sample event below)
                                    'Table': {
                                            'CatalogId': 'string',
                                            'DatabaseName': 'string',
                                            'Name': 'string',
                                            'TableWildcard': {}
                                        }
                                    
        tableWithColumns_json {dict}  --    (sample event below) 
                                        'TableWithColumns': {
                                                'CatalogId': 'string',
                                                'DatabaseName': 'string',
                                                'Name': 'string',
                                                'ColumnNames': [
                                                    'string',
                                                ],
                                                'ColumnWildcard': {
                                                    'ExcludedColumnNames': [
                                                        'string',
                                                    ]
                                                }
                                            }
        perm_json {dict}              --      (sample event below)
                                        Permissions=[
                                        'ALL'|'SELECT'|'ALTER'|'DROP'|'DELETE'|'INSERT'|'DESCRIBE'|
                                        'CREATE_DATABASE'|'CREATE_TABLE'|'DATA_LOCATION_ACCESS'|'CREATE_TAG'|
                                        'ALTER_TAG'|'DELETE_TAG'|'DESCRIBE_TAG'|'ASSOCIATE_TAG',
                                        ]
        perm_grant_json {dict}        --  
                                        PermissionsWithGrantOption=[
                                        'ALL'|'SELECT'|'ALTER'|'DROP'|'DELETE'|'INSERT'|'DESCRIBE'|
                                        'CREATE_DATABASE'|'CREATE_TABLE'|'DATA_LOCATION_ACCESS'|'CREATE_TAG'|
                                        'ALTER_TAG'|'DELETE_TAG'|'DESCRIBE_TAG'|'ASSOCIATE_TAG',
                                        ]   
    """
    principal_json = {}
    table_json = {}
    tableWithColumns_json = {}
    perm_json = {}
    perm_grant_json = {}
    if 'Principal' in event:
        principal_json['DataLakePrincipalIdentifier'] = event['Principal']
    else:
        raise LFAttributeError
    
    if 'Table' in event:
        if 'DatabaseName' not in event['Table']:
            raise LFAttributeError
        table_json['DatabaseName'] = event['Table']['DatabaseName']
        # Need to create a env variable Foundations Account ID
        table_json['CatalogId'] = os.environ['ACCOUNT_ID']
        response = grant_db_describe(principal_json, 
                                            table_json['DatabaseName'])
        if 'foundation_' in table_json['DatabaseName']:
            table_json['DatabaseName']=table_json['DatabaseName'].split('foundation_')[1]
        if 'Name' in event['Table']:
            table_json['Name'] = event['Table']['Name']
        elif 'TableWildcard' in event['Table']:
            table_json['TableWildcard'] = event['Table']['TableWildcard']
        else:
            raise LFAttributeError
    elif 'TableWithColumns' in event:
        if 'DatabaseName' not in event['TableWithColumns']:
            raise LFAttributeError
        tableWithColumns_json['DatabaseName'] = event['TableWithColumns']['DatabaseName']
        tableWithColumns_json['CatalogId'] = os.environ['ACCOUNT_ID']
        response = grant_db_describe(principal_json, 
                                            tableWithColumns_json['DatabaseName'])
        if 'foundation_' in tableWithColumns_json['DatabaseName']:
            tableWithColumns_json['DatabaseName']=tableWithColumns_json['DatabaseName'].split('foundation_')[1]
        if 'Name' not in event['TableWithColumns']:
            raise LFAttributeError
        tableWithColumns_json['Name'] = event['TableWithColumns']['Name']
        if 'ColumnNames' in event['TableWithColumns']:
            tableWithColumns_json['ColumnNames'] = event['TableWithColumns']['ColumnNames']
        elif 'ColumnWildcard' in event['TableWithColumns']:
            tableWithColumns_json['ColumnWildcard'] = event['TableWithColumns']['ColumnWildcard']
        else:
            raise LFAttributeError
    else:
        raise LFAttributeError
    
    if 'Permissions' in event:
        perm_lit = ["SELECT", "DESCRIBE"]
        if list(set(perm_lit) - set(event['Permissions'])):
            logger.info('Found permissions other than SELECT and DESCRIBE ignoring them')
            perm_json['Permissions'] = perm_lit
        else:
            perm_json['Permissions'] = event['Permissions']
    else:
        LFAttributeError
    
    if 'PermissionsWithGrantOption' in event:
        perm_grant_json['PermissionsWithGrantOption'] = ["SELECT", "DESCRIBE"]
        
        
    
    return principal_json, table_json, tableWithColumns_json, perm_json, perm_grant_json


def grant_lf_permissions(principal_json, table_json, tableWithColumns_json, perm_json, perm_grant_json):

    """
    Grants the specified permissions to the Pricncipal on the Respective resources  

    Arguments:
            principal_json  {dict}        -- Principal which requries grant
            table_json       {dict}       -- Resource to grant permissions
            tableWithColumns_json {dict}  -- Resource to grant permissions
            perm_json {dict}              -- permissions that are applied to the resource
            perm_grant_json {dict}        -- grantable permission on the resource
    
    Returns:
        response {dict}    -- Response from Lakeformation API call
    """
    logger.info('Granting Lakeformation Permissions ....')
    try:
        resource = {}
        if table_json:
            resource['Table'] = table_json
        elif tableWithColumns_json:
            resource['TableWithColumns'] = tableWithColumns_json
        if perm_grant_json:
            perm_with_grant = perm_grant_json['PermissionsWithGrantOption']
        else:
            perm_with_grant = []
        client = boto3.client('lakeformation', config=Config(connect_timeout=5, read_timeout=60, retries={'max_attempts': 20}))
        response= client.grant_permissions(Principal=principal_json,
                                Resource=resource,
                                Permissions=perm_json['Permissions'],
                                PermissionsWithGrantOption=perm_with_grant)
        logger.info('Grant permissions API response: {}'.format(response))
        return response
    except Exception as e:
        logger.info("lambda Failed")    
        raise e

def revoke_lf_permissions(principal_json, table_json, tableWithColumns_json, perm_json, perm_grant_json):

    """
    Revokes the specified permissions to the Pricncipal on the Respective resources  

        Arguments:
                principal_json  {dict}        -- Principal which requries grant
                table_json       {dict}       -- Resource to grant permissions
                tableWithColumns_json {dict}  -- Resource to grant permissions
                perm_json {dict}              -- permissions that are applied to the resource
                perm_grant_json {dict}        -- grantable permission on the resource
        Returns:
            response {dict}    -- Response from Lakeformation API call
    
    """
    logger.info('Revoking Lakeformation Permissions ...')
    try:
        resource = {}
        if table_json:
            resource['Table'] = table_json
        elif tableWithColumns_json:
            resource['TableWithColumns'] = tableWithColumns_json
        client = boto3.client('lakeformation', config=Config(connect_timeout=5, read_timeout=60, retries={'max_attempts': 20}))
        response= client.revoke_permissions(Principal=principal_json,
                                Resource=resource,
                                Permissions=perm_json['Permissions'])
        logger.info('Revoke permissions API response: {}'.format(response))
        return response
    except Exception as e:
        logger.info("Revoke permissions Method failed with exception {}".format(e))    
        raise e


def lambda_handler(event, context):
    try:
        logger.info('Received {} messages'.format(len(event['Records'])))
        logger.info('messages {}'.format(event))
        for record in event['Records']:
            event_body = json.loads(json.loads(record['body'])['Message'])['perms_to_set']
            logger.info('Processing Permissions for: {}'.format(event_body))
            principal_json, table_json, tableWithColumns_json, perm_json, perm_grant_json = buildjson(event_body)

        logger.info('created permissions JSONs - principal json : {},table_json {},tableWithColumns_json {}, perm_json {} '
        .format(principal_json, table_json, tableWithColumns_json, perm_json))
        
        if event_body['AccessType'].lower() == 'grant':
            logger.info('Calling Grant permissions for {} on resource {} or {} permissions {}'.format(principal_json, table_json, tableWithColumns_json, perm_json))
            response = grant_lf_permissions(principal_json, table_json, tableWithColumns_json, perm_json, perm_grant_json)
        elif event_body['AccessType'].lower() == 'revoke':
            logger.info('Calling Revoke permissions for {} on resource {} or {} permissions {}'.format(principal_json, table_json, tableWithColumns_json, perm_json))
            response = revoke_lf_permissions(principal_json, table_json, tableWithColumns_json, perm_json, perm_grant_json)
        else:
            raise LFAttributeError

    except Exception as e:
        logger.error("Fatal error", exc_info=True)
        raise e
    return