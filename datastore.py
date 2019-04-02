import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from decimal import Decimal
import sys
import json
import logging
import pprint
import argparse
import verbosity

# Set up logging
logger = logging.getLogger(__name__)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)


class dynamodb(object):

    session_tablename = 'tesla_sessions'

    def __init__(self):
        # Get a dynamodb resource handler
        self.database = boto3.resource('dynamodb')

    def create_sessiontable(self):
        session_KeySchema = [
            {'AttributeName': 'type', 'KeyType': 'HASH'},
            {'AttributeName': 'start_ts', 'KeyType': 'RANGE'}]
        session_AttributeDefinitions = [
            {'AttributeName': 'type', 'AttributeType': 'S'},
            {'AttributeName': 'start_ts', 'AttributeType': 'N'},
            {'AttributeName': 'session_no', 'AttributeType': 'N'}]
        session_ProvisionedThroughput = {
            'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1}
        session_GlobalSecondaryIndexes = [
            {'IndexName': 'session_index',
             'KeySchema': [{'AttributeName': 'session_no', 'KeyType': 'HASH'}],
             'Projection': {'NonKeyAttributes': ["closed", "end_ts"],
                            'ProjectionType': 'INCLUDE'},
             'ProvisionedThroughput': {
                 'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1}
             }]

        self._create_table(self.session_tablename, session_KeySchema,
                           session_AttributeDefinitions,
                           session_ProvisionedThroughput,
                           session_GlobalSecondaryIndexes, False)

    def delete_sessiontable(self):
        self._delete_table(self.session_tablename)

    def sessiontable_exists(self):
        existing_tables = self._get_existing_tables()
        if self.session_tablename in existing_tables:
            return True
        return False

    def add_session(self, session):
        if not self.sessiontable_exists():
            self.create_sessiontable()
        table = self.database.Table(self.session_tablename)
        data = session.__dumpsession__()
        # Dynamodb requires floats to be decimals, use json.dumps to convert
        data = self._mask_nulls(data)
        data = self._py_types_to_dynamodb(data)
        table.put_item(Item=data)
        # pprint.pprint(session.__dumpsession__())

    # def get_last_sessiondata(self):
    #     """ query the session table with the filter"""
    #     sessions = []
    #     query_kw = {'IndexName': 'session_index',
    #                 'FilterExpression': Attr('closed').eq(False)}
    #     table = self.database.Table(self.session_tablename)
    #     result = self._scan_table(table, **query_kw)
    #     if (len(result) == 0):
    #         return None
    #     if len(result) != 1:
    #         raise Exception('Database error, more than one open session')
    #     sessiondata = table.query(
    #         KeyConditionExpression=Key('type').eq(result[0]['type']) &
    #         Key('start_ts').eq(result[0]['start_ts']))
    #     sessiondata = self._dynamodb_types_to_py(sessiondata['Items'][0])
    #     sessiondata = self._unmask_nulls(sessiondata)
    #     return sessiondata

    def get_last_sessiondata(self):
        """ query the session table with the filter"""
        sessions = []
        query_kw = {'IndexName': 'session_index'}
        table = self.database.Table(self.session_tablename)
        results = self._scan_table(table, **query_kw)
        if (len(results) == 0):
            return None
        # Find highest session_no
        top_session = 0
        for result in results:
            if result['session_no'] > top_session:
                top_session = result['session_no']
                last_type = result['type']
                last_start = result['start_ts']

        sessiondata = table.query(
            KeyConditionExpression=Key('type').eq(last_type) &
            Key('start_ts').eq(last_start))
        sessiondata = self._dynamodb_types_to_py(sessiondata['Items'][0])
        sessiondata = self._unmask_nulls(sessiondata)
        return sessiondata

    def _scan_table(self, table, **kwargs):
        """ scan the table with the filter"""
        sessions = []
        retries = 0
        while True:
            try:
                response = table.scan(**kwargs)
                sessions.extend(response['Items'])
                last_key = response.get('LastEvaluatedKey')
                if not last_key:
                    break
                retries = 0     # if successful, reset count
                scan_kw.update({'ExclusiveStartKey': last_key})
            except ClientError as err:
                if err.response['Error']['Code'] not in RETRY_EXCEPTIONS:
                    raise
                print('Too fast, slow it down retries={}'.format(retries))
                sleep(2 ** retries)
                retries += 1
        sessions = self._unmask_nulls(sessions)
        sessions = self._dynamodb_types_to_py(sessions)
        return sessions

    def _query_table(self, table, **kwargs):
        """ query the table with the filter"""
        sessions = []
        retries = 0
        while True:
            try:
                response = table.query(**kwargs)
                sessions.extend(response['Items'])
                last_key = response.get('LastEvaluatedKey')
                if not last_key:
                    break
                retries = 0     # if successful, reset count
                scan_kw.update({'ExclusiveStartKey': last_key})
            except ClientError as err:
                if err.response['Error']['Code'] not in RETRY_EXCEPTIONS:
                    raise
                print('Too fast, slow it down retries={}'.format(retries))
                sleep(2 ** retries)
                retries += 1
        sessions = self._unmask_nulls(sessions)
        sessions = self._dynamodb_types_to_py(sessions)
        return sessions

    def _query_sessions(self, filter=None):
        """ query the session table with the filter"""
        query_kw = {}
        sessions = []
        if filter:
            query_kw.update({'FilterExpression': filter})
        retries = 0
        table = self.database.Table(self.session_tablename)
        while True:
            try:
                response = table.scan(**query_kw)
                sessions.extend(response['Items'])
                last_key = response.get('LastEvaluatedKey')
                if not last_key:
                    break
                retries = 0     # if successful, reset count
                query_kw.update({'ExclusiveStartKey': last_key})
            except ClientError as err:
                if err.response['Error']['Code'] not in RETRY_EXCEPTIONS:
                    raise
                print('Too fast, slow it down retries={}'.format(retries))
                sleep(2 ** retries)
                retries += 1
        sessions = self._unmask_nulls(sessions)
        sessions = self._dynamodb_types_to_py(sessions)
        return sessions

    def _create_table(self, table_name, key_schema, attribute_definitions,
                      provisioned_throughput, secondary_indexes, killdb):
        """ Create the DynamoDB Table """
        logger.debug(
            'In create_table, attempting to create {}'.format(table_name))
        if killdb:
            self._delete_table(table_name)
        logger.info('Attempting to create table {}'.format(table_name))
        try:
            table = self.database.create_table(
                TableName=table_name,
                KeySchema=key_schema,
                AttributeDefinitions=attribute_definitions,
                ProvisionedThroughput=provisioned_throughput,
                GlobalSecondaryIndexes=secondary_indexes
            )
            # Wait until the table exists.
            table.meta.client.get_waiter(
                'table_exists').wait(TableName=table_name)
        except ClientError as e:
            logger.error("Unexpected error: {}".format(e))
            return False
        logger.info('Table {} created'.format(table_name))
        return table

    def _delete_table(self, table_name):
        logger.debug(
            'Trying to delete existing table {}'.format(table_name))
        table = self.database.Table(table_name)
        table.delete()
        table.meta.client.get_waiter(
            'table_not_exists').wait(TableName=table_name)
        logger.info('Table {} Deleted'.format(table_name))

    def _get_existing_tables(self):
        # Get existing DynamoDB table names
        tables = []
        for i_table in self.database.tables.all():
            tables.append(i_table.table_name)
        logger.info('found existing table names {}'.format(tables))
        return tables

    def _mask_nulls(self, d):
        """ Recurse dict item and sub-dicts and sub-lists to remove
            empty values.  (Requirement for DynamoDB) """
        if not isinstance(d, (dict, list)):
            if d is None:
                return 'NonePlace'
            if d == '':
                return 'EmptyString'
            return d
        if isinstance(d, list):
            return [v for v in (self._mask_nulls(v) for v in d)]
        return {k: v for k, v in ((k, self._mask_nulls(v))
                                  for k, v in d.items())}

    def _unmask_nulls(self, d):
        """ Add back masked nulls  (Requirement for DynamoDB) """
        if not isinstance(d, (dict, list)):
            if d == 'NonePlace':
                return None
            if d == 'EmptyString':
                return ''
            return d
        if isinstance(d, list):
            return [v for v in (self._unmask_nulls(v) for v in d)]
        return {k: v for k, v in ((k, self._unmask_nulls(v))
                                  for k, v in d.items())}

    def _py_types_to_dynamodb(self, d):
        """ Convert Python types to be DynamoDB compatible - recurse """
        if not isinstance(d, (dict, list)):
            if isinstance(d, float):
                return Decimal(str(d))
            return d
        if isinstance(d, list):
            return [v for v in (self._py_types_to_dynamodb(v) for v in d)]
        return {k: v for k, v in ((k, self._py_types_to_dynamodb(v))
                                  for k, v in d.items())}

    def _dynamodb_types_to_py(self, d):
        """ Convert DynamoDB types to python - recurse """
        if not isinstance(d, (dict, list)):
            if isinstance(d, Decimal):
                if abs(d % 1) > 0:
                    return float(d)
                else:
                    return int(d)
            else:
                return d
        if isinstance(d, list):
            return [v for v in (self._dynamodb_types_to_py(v) for v in d)]
        return {k: v for k, v in ((k, self._dynamodb_types_to_py(v))
                                  for k, v in d.items())}


def main():
    parser = argparse.ArgumentParser()
    # parser.add_argument('--verbose', '-v', action='count',
    #                     help='Increasing levels of verbosity')
    parser.add_argument('--erasedb', action='store_true',
                        help='Do not print summary information')
    parser.add_argument('-l', '--localdb', action='store_true',
                        help='use local database', required=False)
    parser.add_argument('-si', '--sessionindex', action='store_true',
                        help='show sessionindex')
    verbosity.add_arguments(parser)
    args = parser.parse_args()

    # initialize logging handle logging arguments
    verbosity.initialize(logger)
    verbosity.handle_arguments(args, logger)

    if args.erasedb:
        d = dynamodb()
        d.delete_sessiontable()

    if args.sessionindex:
        d = dynamodb()
        # query_kw = {'IndexName': 'session_index',
        #             'KeyConditionExpression': Key('session_no').eq(1),
        #             'ScanIndexForward': True}
        # table = d.database.Table(d.session_tablename)
        # print(d._scan_table(table, **query_kw))
        print(d.get_last_sessiondata())
        # table = d.database.Table(d.session_tablename)
        # print(d._query_table(table, **query_kw))


if __name__ == "__main__":
    main()
