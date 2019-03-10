import time
import subprocess
import boto3
from threading import Lock


class Writer:
    """ Class handling different outuput options """

    def add_channel(self, type, location):
        """ Add an output channel to the writer """
        ''' Types of channels
            outdir = directory for rotating json - pass in folder to manage
            stream = output raw, no file rotation - pass in file handle
            firehose = write to AWS Kinesis firehose - pass in kineisis stream
        '''
        self.output_channels.append({'type': type,
                                     'location': location})

    def write(self, data):
        """Write to the known output channels"""
        # Map functions to known output types
        options = {'outdir': self.__write_to_file,
                   'stream': self.__write_to_stream,
                   'firehose': self.__write_to_firehose
                   }
        # For each channel, call theh appropriate writer for the type
        # using a while with index, safe way to modify the list whle being
        # iterated on
        for i in range(len(self.output_channels)):
            options[self.output_channels[i]['type']](data, i)

    def channelcount(self):
        """ Return number of current channels """
        return len(self.output_channels)

    def __init__(self):
        self.output_channels = []
        self.nexthour = 0
        self.master_lock = Lock()

    def __write_to_file(self, data, channel_index):
        # do maint and determine the current filehandle & update the record
        filehandle = self.__output_maintenance(
            self.output_channels[channel_index]['location'],
            self.output_channels[channel_index].get('handle'))
        self.output_channels[channel_index].update({'handle': filehandle})
        filehandle.write(data)
        filehandle.flush()

    def __write_to_stream(self, data, channel_index):
        # For streams (e.g. stdout), filehandle is passed as location
        stream = self.output_channels[channel_index].get('location')
        stream.write(data)
        stream.flush()

    def __write_to_firehose(self, data, channel_index):
        firehose = self.output_channels[channel_index].get('firehose')
        if not firehose:
            firehose = boto3.client('firehose')
            self.output_channels[channel_index].update({'firehose': firehose})
        response = firehose.put_record(
            DeliveryStreamName=self.output_channels[channel_index].get(
                'location'),
            Record={'Data': data}
        )

    def __output_maintenance(self, outdir, outfile):
        """Move to the next output file when time, close/reopen every hour"""
        cur = time.time()

        # Ensure we don't have multi-vehicle output direct race conditions
        with self.master_lock:
            if cur < self.nexthour:
                return outfile
            if outfile is not None:
                outfile.close()
            self.nexthour = (int(cur / 3600) + 1) * 3600
            fname = time.strftime("%Y-%m-%d.json", time.gmtime(cur))
            pname = "{}/{}".format(outdir, fname)
            # W = open(pname, "a", 0)
            outfile = open(pname, "a")
            subprocess.call(["ln", "-sf", fname,
                             "{}/cur.json".format(outdir)])
            return outfile
