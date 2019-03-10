#!/usr/bin/env python3
#
# Print the data stored by tesla_poller
#

import argparse
import datetime
import pytz
import subprocess
import json
import sys
import logging
import verbosity
from tesla_parselib import TeslaRecord, TeslaSession

logger = logging.getLogger(__name__)

nexthour = 0
X = None
firstthismode = None
lastprevmode = None
save = None
lastthis = None
reallasttime = None
args = None


class openfile(object):
    """Open a file or tail a file, return file descriptor"""

    def __init__(self, filename, args):
        self.filename = filename
        if filename:
            self.fd = open(filename, "r")
            self.sub = None
        else:
            # Follow the file
            self.sub = subprocess.Popen(
                ['tail', '-n', args.numlines, '-F', args.follow],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.fd = self.sub.stdout

    def __enter__(self):
        return self.fd

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.filename:
            self.fd.close()
        else:
            self.sub.kill()


def output_maintenance(cur):
    """ Move to the next output file when time, close/reopen every hour"""
    global nexthour, X
    import time
    if not args.outdir:
        return
    if cur < nexthour:
        return
    if X is not None:
        X.close()
    nexthour = (int(cur / 3600) + 1) * 3600
    fname = time.strftime("%Y-%m-%d.json", time.gmtime(cur))
    pname = "%s/%s" % (args.outdir, fname)
    X = open(pname, "a", 0)
    subprocess.call(["ln", "-sf", fname, "%s/cur.json" % args.outdir])


def outputit(this):
    if this.usable_battery_level:
        bat = "%3d%%/%.2fM" % (this.usable_battery_level, this.battery_range)
    else:
        bat = ""

    if this.charge_energy_added:
        add = "%5.2f/%.1fM" % (this.charge_energy_added,
                               this.charge_miles_added)
    else:
        add = ""

    if this.charge_rate:
        rate = "%dkW/%dM" % (this.charger_power or 0, this.charge_rate)
    else:
        rate = ""

    return("%s %-8s odo=%-7s spd=%-3s bat=%-12s chg@%-12s add=%s" %
           (datetime.datetime.fromtimestamp(this.timets).strftime('%Y-%m-%d %H:%M:%S'),
            this.mode,
            "%.2f" % this.odometer if this.odometer else "",
            str(this.speed or ""),
            bat,
            rate,
            add))


def analyzer(this, firstthismode, lastprevmode, save, lastthis, reallasttime):
    """ Analyze the status, tracking state and providing outputs

    Parameters:
        this(cls): object with the current data
        firstthismode(cls): first object in the current mode
        lastprevmode(cls): last object before the current mode
        save(cls): Not sure yet
        lastthis(cls): Not sure yet
        reallasttime(time): timestamp from start of current mode


    Returns:
        updated: firstthismode, lastprevmode, save, lastthis, reallasttime)
    """

    # if vehicle is Polling (offline) exit quickly.
    if this.mode == "Polling":
        reallasttime = this.timets
        logger.debug('\n{}'.format(outputit(this)))
        exit()
        return (firstthismode, lastprevmode, save, lastthis, reallasttime)

    if save:
        save = save + this
    else:
        save = this
        prev = this

    # analyze data and provide a summary
    while firstthismode and not args.nosummary:
        # Detect a change in mode
        if firstthismode.mode != this.mode:
            # jsp: looks to change the timets in the current object to be the
            # timestamp of from the beginning of the last mode.  why?
            if reallasttime:
                this.timets = reallasttime
                reallasttime = None
            firstthismodetime = datetime.datetime.fromtimestamp(
                firstthismode.timets)
            thistime = datetime.datetime.fromtimestamp(save.timets)

            # If we don't know the end of the previous mode or don't have
            # Battery and odometer levels, can't do much
            if (not lastprevmode or
                    not lastprevmode.usable_battery_level or
                    not lastprevmode.odometer):
                print("%s            ending %s, but did not have previous state to compute deltas" %
                      (firstthismodetime.strftime('%Y-%m-%d %H:%M:%S'), firstthismode.mode))

            # Did we just leave a "Charging" mode?
            elif firstthismode.mode == "Charging":
                battery_range = (save.battery_range
                                 if save.battery_range > lastthis.battery_range
                                 else lastthis.battery_range)
                # if this.usable_battery_level > save.usable_battery_level:
                #     usable_battery_level = this.usable_battery_level
                # elif save.usable_battery_level > lastthis.usable_battery_level:
                #     usable_battery_level = save.usable_battery_level
                # else:
                #     usable_battery_level = lastthis.usable_battery_level

                usable_battery_level = (save.usable_battery_level
                                        if save.usable_battery_level
                                        > lastthis.usable_battery_level
                                        else lastthis.usable_battery_level)

                dblevel = usable_battery_level - lastprevmode.usable_battery_level

                print("%s +%-16s Charged   %3d%% (to %3d%%) %5.2fkW %5.1fM (%3dmph, %4.1fkW %5.1fM max)" %
                      (firstthismodetime.strftime('%Y-%m-%d %H:%M:%S'),
                       str(thistime - firstthismodetime),
                       dblevel,
                       usable_battery_level,
                       save.charge_energy_added,
                       battery_range - lastprevmode.battery_range,
                       ((battery_range - lastprevmode.battery_range) * 3600.0
                        / (thistime - firstthismodetime).total_seconds()),
                       (save.charge_energy_added * 100.0 /
                        (dblevel)) if dblevel > 0 else -0,
                       battery_range * 100.0 / save.usable_battery_level))
            elif firstthismode.mode == "Driving":
                if not this.odometer:
                    break
                battery_range = save.battery_range if save.battery_range < lastthis.battery_range else lastthis.battery_range
                usable_battery_level = save.usable_battery_level if save.usable_battery_level < lastthis.usable_battery_level else lastthis.usable_battery_level
                dodo = save.odometer - lastprevmode.odometer
                drange = lastprevmode.battery_range - battery_range

                if dodo > -1:
                    print("%s +%-19s Drove  %6.2fM at cost of %2.0f%% %5.1fM at %5.1f%% efficiency" %
                          (firstthismodetime.strftime('%Y-%m-%d %H:%M:%S'),
                           str(thistime - firstthismodetime),
                           dodo,
                           lastprevmode.usable_battery_level - usable_battery_level,
                           drange,
                           dodo * 100.0 / drange if drange > 0 else -0))
            elif firstthismode.mode == "Standby":
                battery_range = save.battery_range if save.battery_range < lastthis.battery_range else lastthis.battery_range
                usable_battery_level = lastthis.usable_battery_level
                drange = lastprevmode.battery_range - battery_range
                print("%s +%-19s Parked %2.0f%% %5.1fM or %5.1fM/d (to %3d%%)" %
                      (firstthismodetime.strftime('%Y-%m-%d %H:%M:%S'),
                       str(thistime - firstthismodetime),
                       lastprevmode.usable_battery_level - usable_battery_level,
                       drange,
                       drange /
                       (((thistime - firstthismodetime).total_seconds()) / 86400.0),
                       usable_battery_level))
            elif firstthismode.mode == "Conditioning":
                battery_range = save.battery_range if save.battery_range < lastthis.battery_range else lastthis.battery_range
                usable_battery_level = lastthis.usable_battery_level
                drange = lastprevmode.battery_range - battery_range
                print("%s +%-19s Conditioned %2.0f%% %5.1fM or %5.1fM/d (to %3d%%)" %
                      (firstthismodetime.strftime('%Y-%m-%d %H:%M:%S'),
                       str(thistime - firstthismodetime),
                       lastprevmode.usable_battery_level - usable_battery_level,
                       drange,
                       drange /
                       (((thistime - firstthismodetime).total_seconds()) / 86400.0),
                       usable_battery_level))

            else:
                print("Do not handle mode %s" % firstthismode.mode)
            firstthismode = save
            lastprevmode = lastthis
        break
    else:
        reallasttime = None
        firstthismode = save
        lastprevmode = save
    lastthis = save

    logger.debug('{}'.format(outputit(this)))

    return (firstthismode, lastprevmode, save, lastthis, reallasttime)


def main():
    global firstthismode, lastprevmode, save, lastthis, reallasttime, args
    session = None
    parser = argparse.ArgumentParser()
    # parser.add_argument('--verbose', '-v', action='count',
    #                     help='Increasing levels of verbosity')
    parser.add_argument('--nosummary', action='store_true',
                        help='Do not print summary information')
    parser.add_argument('--follow', '-f', type=str,
                        help='Follow this specific file')
    parser.add_argument('--numlines', '-n', type=str,
                        help='Handle these number of lines')
    parser.add_argument('--timezone', default=None,
                        help='Timezone for output, defaults to local')
    parser.add_argument('--outdir', default=None,
                        help='Convert input files into daily output files')
    parser.add_argument('files', nargs='*')
    verbosity.add_arguments(parser)
    args = parser.parse_args()

    # initialize logging handle logging arguments
    verbosity.initialize(logger)
    verbosity.handle_arguments(args, logger)

    # if args.verbose is None:
    #     args.verbose = 0

    if not args.numlines:
        args.numlines = "10"

    if args.follow:
        args.files.append(None)

    # Get timezone to use for output (default to local)
    if args.timezone:
        tzone = pytz.timezone(args.timezone)
    else:
        tzone = datetime.datetime.now().astimezone().tzinfo

    # loop over all files
    for fname in args.files:
        with openfile(fname, args) as R:
            linenum = 0
            # loop over all json records (one per line)
            while True:
                # read a line
                line = R.readline()
                linenum += 1
                if not line:
                    break
                # parse the json into 'this' object
                # this = TeslaRecord(line, want_offline=args.verbose > 2)
                this = TeslaRecord(line)

                # if no valid object move on to the next
                if not this:
                    continue

                # output data to file in outdir
                if args.outdir:
                    output_maintenance(this.timets)
                    X.write(line)

                # outputit(this)

                # If car is asleep, move along - TODO
                if this.mode == "Polling":
                    continue

                # Initialize first session if needed
                if session is None:
                    session = TeslaSession.create(this, tzone=tzone)

                # Check for a state change
                if this.session_type == session.type:
                    # update the session with data from current record
                    session.update(this)
                    since_last = session.since_last
                else:
                    # We have a state change, start new session
                    session.close(this)
                    session.pprint()
                    session = TeslaSession.create(this, tzone=tzone)
                    since_last = session.since_last

                if since_last > 12000:
                    fmt = '{} ({}s)since last record. sess:({}), ts:{}, {}'
                    logger.debug(fmt.format(
                        datetime.timedelta(seconds=since_last),
                        since_last,
                        session.session_no,
                        this.timets,
                        session._fmt_ts(this.timets)))

                # (firstthismode, lastprevmode, save, lastthis, reallasttime) = analyzer(
                #     this, firstthismode, lastprevmode, save, lastthis, reallasttime)


if __name__ == "__main__":
    main()
