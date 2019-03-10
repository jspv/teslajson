import boto3
import pprint
import argparse
import verbosity
import logging

# class Reader:
#     """ Class handling reading from different input options """
#
#     # s3  format teslastats/YYYY/MM/DD/HH/teslastats-1-YYYY-MM-DD-HH-MM-SS-*
#
logger = logging.getLogger(__name__)


def get_matching_s3_keys(bucket, prefix='', suffix=''):
    """ Generate the keys in an S3 bucket.
    (thanks https://alexwlchan.net/2017/07/listing-s3-keys/)
    This is a generator using yield so that it can be called repetatively
    unil exhaused.

    :param bucket: Name of the S3 bucket.
    :param prefix: Only fetch keys that start with this prefix (optional).
    :param suffix: Only fetch keys that end with this suffix (optional).
    """
    s3 = boto3.client('s3')
    kwargs = {'Bucket': bucket}

    # If the prefix is a single string (not a tuple of strings), we can
    # do the filtering directly in the S3 API.
    if isinstance(prefix, str):
        kwargs['Prefix'] = prefix

    while True:

        # The S3 API response is a large blob of metadata.
        # 'Contents' contains information about the listed objects.
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp['Contents']:
            key = obj['Key']
            if key.startswith(prefix) and key.endswith(suffix):
                yield key

        # The S3 API is paginated, returning up to 1000 keys at a time.
        # Pass the continuation token into the next response, until we
        # reach the final page (when this field is missing).
        try:
            kwargs['ContinuationToken'] = resp['NextContinuationToken']
        except KeyError:
            break


def get_matching_s3_objects(bucket, prefix='', suffix=''):
    """ Generate the objects in an S3 bucket.
    (thanks https://alexwlchan.net/2017/07/listing-s3-keys/)
    This is a generator using yield so that it can be called repetatively
    unil exhaused.

    :param bucket: Name of the S3 bucket.
    :param prefix: Only fetch keys that start with this prefix (optional).
    :param suffix: Only fetch keys that end with this suffix (optional).
    """
    s3 = boto3.client('s3')
    s3res = boto3.resource('s3')
    kwargs = {'Bucket': bucket}

    # If the prefix is a single string (not a tuple of strings), we can
    # do the filtering directly in the S3 API.
    if isinstance(prefix, str):
        kwargs['Prefix'] = prefix

    while True:

        # The S3 API response is a large blob of metadata.
        # 'Contents' contains information about the listed objects.
        resp = s3.list_objects_v2(**kwargs)
        if 'Contents' in resp:
            for obj in resp['Contents']:
                key = obj['Key']
                if key.startswith(prefix) and key.endswith(suffix):
                    s3obj = s3res.Object(bucket, key)
                    yield s3obj

        # The S3 API is paginated, returning up to 1000 keys at a time.
        # Pass the continuation token into the next response, until we
        # reach the final page (when this field is missing).
        try:
            kwargs['ContinuationToken'] = resp['NextContinuationToken']
        except KeyError:
            break


def main():
    args = None
    parser = argparse.ArgumentParser()
    parser.add_argument('--bucket', required=True, help='bucketname')
    parser.add_argument('--prefix', required=False, default='',
                        help='Optional prefix, post-prefix should '
                             'start with YYYY/')
    parser.add_argument('daterange', nargs='*',
                        help="Range of dates")
    verbosity.add_arguments(parser)
    args = parser.parse_args()

    # initialize logging handle logging arguments
    verbosity.initialize(logger)
    verbosity.handle_arguments(args, logger)

    for date in args.daterange:
        fullprefix = args.prefix + date
        for object in get_matching_s3_objects(bucket=args.bucket,
                                              prefix=fullprefix):
            print(object.get()["Body"].read().decode('utf-8'))


if __name__ == "__main__":
    main()
