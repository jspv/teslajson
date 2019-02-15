#!/usr/bin/env python3
import time
import json
import argparse
import re
import secrets
import os
import errno
# from time import strftime
from sys import stdin


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--streamname', help='Name of stream',
                        required=True)
    parser.add_argument('--mins', help="minutes in each file (max 60)",
                        default=5, type=int)
    args = parser.parse_args()

    # Read each line from stdin keying on fromtime
    lastfilebase = ''
    outfile = None
    for line in stdin:
        # find timestamp
        if line[:1] == '{':
            record = json.loads(line)
            tstamp = int(record['retrevial_time'])
            # print('time is {}'.format(record.get('retrevial_time')))
        if line[:1] == '#':
            ts = re.match(r"^# (\d{10})[\. ]", line)
            if not ts:
                ts = re.search(r"\) at (\d{10}$)", line)
            if not ts:
                print(line)
                quit(1)
            tstamp = int(ts.group(1))
            # print('time is {}'.format(ts.group(1)))

        # Rollback minutes to last 5m mark
        minutes = int(time.strftime('%M', time.gmtime(tstamp)))
        minutes = minutes - (minutes % args.mins)

        # Build the filepath
        timepath = time.strftime('%Y,%m,%d,%H', time.gmtime(tstamp))
        outfiledir = os.path.join(args.streamname, *timepath.split(','))
        # outfilebase is the first part before the random strings are
        # added.
        outfilebase = ('{}-1-{}-{:02d}-00'
                       .format(args.streamname,
                               time.strftime(
                                   '%Y-%m-%d-%H', time.gmtime(tstamp)),
                               minutes))
        if (lastfilebase != outfilebase):
            # Time to create a new file
            if outfile is not None:
                outfile.close()
            outfilename = '{}-{}-{}-{}-{}'.format(outfilebase,
                                                  secrets.token_hex(4),
                                                  secrets.token_hex(2),
                                                  secrets.token_hex(2),
                                                  secrets.token_hex(4))
            if not os.path.exists(outfiledir):
                try:
                    os.makedirs(outfiledir)
                except OSError as e:
                    if e.error != errno.EEXIST:
                        raise
            outfilepath = os.path.join(outfiledir, outfilename)
            outfile = open(outfilepath, "w")
            lastfilebase = outfilebase
            print(outfilepath)
        outfile.write(line)


if __name__ == "__main__":
    main()
