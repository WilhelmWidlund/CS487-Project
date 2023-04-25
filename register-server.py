import argparse
from tango import Database, DbDevInfo

# This script registers device servers for all paint tanks and mixing tank of one selected station
parser = argparse.ArgumentParser(
                    prog='register-server.py',
                    description='Register device server with Tango')
parser.add_argument('station_name', help='a name of the paint mixing station (e.g. station1)')

args = parser.parse_args()

#  reference to the Tango database
db = Database()

for device_name in ["cyan", "magenta", "yellow", "black", "white", "mixer"]:
    device_info = DbDevInfo()
    # define the Tango Class served by this device server
    device_info._class = "PaintTank"
    # define the instance name for the device server
    device_info.server = "PaintMixingStation/%s" % args.station_name
    # define the device name
    device_info.name = "epfl/station1/%s" % device_name
    db.add_device(device_info)