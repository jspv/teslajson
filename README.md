# teslatools
Simple Python class to access the Tesla JSON API and related tools to poll, store, and report on the data.

## Project Goals
0. Modify the code originally written by and forked from Greg Glockner to
support logging vehicle output to AWS S3 via Kinesis Firehose. (**complete**)
0. Update Greg's parser tools to work from S3 datastore (in progress)
0. Create automation/cloudformations to:
  0. Build and setup Kinesis delivery stream and associated policy for write access (**complete**)
  0. Dedicated S3 bucket for the stream as well as a separate area for storing token data and an area for static html-based tools (not started)
  0. Lambda or similar to parse and index the JSON data (not started)
  0. Scrips to easily add the poller to an EC2 instance (not started)
0. S3 based HTML tools to access and report on vehicle data (not started)

# Tool Descriptions

## teslajson.py

This is a simple Python interface to the [Tesla JSON
API](https://tesla-api.timdorr.com/). With this, you can query your
vehicle, control charge settings, turn on the air conditioning, and
more.  You can also embed this into other programs to automate these
controls.

The class is designed to be simple.  You initialize a _Connection_
object, retrieve the list of _Vehicle_ objects, then perform get/set
methods on a _Vehicle_.  There is a single get method
[_Vehicle.data\_request()_] and a single set method [_Vehicle.command()_] so
that the class does not require changes when there are minor updates
to the underlying JSON API.

This has been tested Python 3.6.  It has no dependencies beyond the standard Python libraries.

#### Installation
0. Download the repository zip file and uncompress it
0. Run the following command with your Python interpreter: `python setup.py install`

Alternately, add the teslajson.py code to your program.

#### Public API
`Connection(email, password, **kwargs)`:
Initialize the connection to the Tesla Motors website.

Required parameters:

- Option one:

  - _userid_: your login for teslamotors.com, you will be prompted to enter the password

- Option two: (May be combined with option one to create a new tokenfile)

  - _tokenfile_: A file containing json token authentication data as tesla generates.  It will automatically be updated when it expires.

- Option three:

  - _accesstoken_: An active access token for your account.  May expire.


Optional parameters:
- _proxy\_url_: URL for proxy server
- _proxy\_user_: username for proxy server
- _proxy\_password_: password for proxy server
- _retries_: number of times to retry request before failing
- _retry\_delay_: multiplicative backoff on failure
- _tesla\_client_: Override API retrevial from pastebin
- _debug_: Activate debugging, add more to debug
- _vid_: Vehicle to operate on, if you have multiple vehicles

`Connection.vehicles`: A list of Vehicle objects, corresponding to the
vehicles associated with your account on teslamotors.com.

`Vehicle`: The vehicle class is a subclass of a Python dictionary
(_dict_).  A _Vehicle_ object contains fields that identify your
vehicle, such as the Vehicle Identification Number (_Vehicle['vin']_).
All standard dictionary methods are supported.

`Vehicle.wake_up()`: Wake the vehicle.

`Vehicle.data_all()`: Retrieve all data values associated with vehicle.

`Vehicle.data_request(name)`: Retrieve data values specified by _name_, such
as _charge\_state_, _climate\_state_, _vehicle\_state_. Returns a
dictionary (_dict_).  For a full list of _name_ values, see the _GET_
commands in the [Tesla JSON API](http://docs.timdorr.apiary.io/).

`Vehicle.command(name)`: Execute the command specified by _name_, such
as _charge\_port\_door\_open_, _charge\_max\_range_. Returns a
dictionary (_dict_).  For a full list of  _name_ values, see the _POST_ commands
in the [Tesla JSON API](http://docs.timdorr.apiary.io/).

#### Example
	import teslajson
	c = teslajson.Connection('youremail', 'yourpassword')
	v = c.vehicles[0]
	v.wake_up()
	v.data_request('charge_state')
	v.command('charge_start')

#### Partial example:

	c = teslajson.Connection(access_token='b5bb9d8014a0f9b1d61e21e796d78dccdf1352f23cd32812f4850b878ae4944c', tesla_client='{"v1": {"id": "e4a9949fcfa04068f59abb5a658f2bac0a3428e4652315490b659d5ab3f35a9e", "secret": "c75f14bbadc8bee3a7594412c31416f8300256d7668ea7e6e7f06727bfb9d220", "baseurl": "https://owner-api.teslamotors.com", "api": "/api/1/"}}')

#### Another example

	./teslajson.py --userid my@email.com --tokens_file /tmp/tesla.creds get
  (get prompted for password)
	./teslajson.py --tokens_file /tmp/tesla.creds --vid 0 get
	./teslajson.py --tokens_file /tmp/tesla.creds --retries 10 do wake_up
	./teslajson.py --tokens_file /tmp/tesla.creds get climate_state
	./teslajson.py --tokens_file /tmp/tesla.creds get gui_settings
	./teslajson.py --tokens_file /tmp/tesla.creds get mobile_enabled
	./teslajson.py --tokens_file /tmp/tesla.creds get data
	./teslajson.py --tokens_file /tmp/tesla.creds do charge_port_door_open


#### Credits
Many thanks to [Tim Dorr](http://timdorr.com) for documenting the Tesla JSON API.
This would not be possible without his work.

#### Disclaimer
This software is provided as-is.  This software is not supported by or
endorsed by Tesla Motors.  Tesla Motors does not publicly support the
underlying JSON API, so this software may stop working at any time.  The
author makes no guarantee to release an updated version to fix any
incompatibilities.

--------------------

## tesla_poller

Originally written by Seth Robertson, modified by jspv to support AWS Kinesis delivery streams, simplified to just query the Tesla API and write the output to the designated targets, removed the original capability to send commands and the "insecure network API"

tesla_poller uses the teslajson library to do smart polling of your Tesla(s) and log the resulting JSON information to a directory and/or AWS Kinesis stream for post-processing. It will change polling frequency depending on what you are doing (e.g. driving, charging, pre-heating, nothing, etc).

Required parameters:

- Option one:

  - _userid_: your login for teslamotors.com, you will be prompted for the password

- Option two: (May be combined with option one to create a new tokenfile)

  - _tokenfile_: A file containing json token authentication data as tesla generates.  It will automatically be updated when it expires.

- Option three:

  - _accesstoken_: An active access token for your account.  May expire.


Command line arguments are requried for authentication: `--token`,
`--tokenfile`, or `--userid`

Optional parameters:
- _outdir_: Directory to place json log files
- _firehose_: Kinesis Firehose delivery stream to send json data to

In order to log the data, supply an output directory with `--outdir
path`.  In addition to a file named by YEAR-MON-DAY.json, there is a
symlink cur.json to the most recent file.

You may override the intervals of important (polling frequency mostly)
by using `--intervals inactive=61` or similar.

---------

## Reading the stored data

`tesla-parser.py` was created to read the stored data.

Example usage: `tesla-parser.py /path/to/cur.json`

By default it provides summary information for drives you make,
charges you do, and standby times.

If you want to see more detailed information, use `-v`.  Add another
`-v` or two to learn about even less important activity.

You may supply multiple files, and you may use the `-f` argument to
follow a file as it is appended to.  A convenient way to dump all
historical information and then start printing any future information
is:

`tesla-parser.py -f /var/logs/tesla/cur.json -n 0 /var/logs/tesla/20*.json`

Example output:

    2018-07-07 08:50:56 +0:20:04 Drove   20.58M at cost of 10% 25.4M at  80.9% efficiency
    2018-07-07 09:16:00 +4:55:03 Sat&Lost  2%  15.8M or  77.2M/d
    2018-07-07 14:11:03 +0:22:08 Drove   20.33M at cost of  8% 20.2M at 100.4% efficiency
    2018-07-07 14:38:11 +0:12:12 Sat&Lost  0%   0.0M or   0.0M/d
    2018-07-07 14:50:23 +2:32:50 Charged  25% (to  88%) 19.37kW  79.1M ( 31mph, 77.5kW 311.8M max)

In the above example, the vehicle started on a 20 mile trip at 8:50
am, which took 20 minutes.  It actually use 25 rated miles of range
(10% of battery), meaning 81% efficiency.

The vehicle then sat for 5 hours and lost 2% of charge (16 rated
miles) for a 77 miles per day effective rate (perhaps cabin
temperature control was enabled).

There was a 22 minute return trip, this time at 100% efficiency. The
vehicle sat for 12 minutes (not losing any power), and then was
charged for 2.5 hours, to 88%, getting 19kW or 79 rated miles.  The
charge was obtained at an average speed of 31mph, and implied a
fully charged battery size of 78kW and a 312 maximum rated mile range.

## Storing the data in a relational database

`tesla-parser.py` is able to insert the stored data into a relational
database which may be more convenient for analysis. In order to do this
an adequate Postgresql database needs to be installed and accessible.
Create a database named "tesladata" and set a user (eg. "teslauser")
with privileges to create tables. Then run the file `create_tables`
with this user. Set the connection details in the file `dbconfig`,
including the password for the user (it is advisible to have that file
protected from other users so as not to reveal the password).

`create user teslauser with encrypted password 'example'`;
`create database tesladata;`
`grant all privileges on database tesladata to teslauser;`
`psql -U testauser testladata < create_tables.sql`

To store the data into the database run `tesla-parser.py` with the
command line option `--dbconfig dbconfig`. Instead of dumping
summary statistics this will instead insert the data into
the database. Make sure to indicate the file(s) with the data desired.
For example:

`tesla-parser.py -n 0 --dbconfig dbconfig /var/logs/tesla/20*.json`

If the data had already been inserted into the database in a previous
run, the program will issue appropriate warnings.

-----------------
## json2s3.py - Converting default JSON output to AWS Kinesis style

`json2s3.py` will take the output JSON output files created by `tesla-poller` and will write out a formatted directory and file structure used in the S3 repository of the AWS Kinesis delivery stream.  You can use this to reformat historical records so that they can be copied over to the S3 bucket and be compatible with new files created by Kinesis.

Output format is: streamname/YYYY/MM/DD/HH/streamname-1-YYYY-MM-DD-HH-mm-{hex8}-{hex4}-{hex4}-{hex4}-{hex12} where {hex#} is a number of random hex digits.

Required parameters:

- _streamname_: name of the Kinesis stream, used to format the output files

Optional parameters:

  - _mins_: The number of minutes of data to store in each file, default is to write a new file for every 5 minutes of data.

# Bugs

Only tested with one vehicle.
