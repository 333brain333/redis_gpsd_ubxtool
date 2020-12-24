from gps import *
import time

running = True

def getPositionData(gps):
    nx = gps.next()
    # For a list of all supported classes and fields refer to:
    # https://gpsd.gitlab.io/gpsd/gpsd_json.html
    if nx['class'] == 'TPV':
        latitude = getattr(nx,'lat', "Unknown")
        longitude = getattr(nx,'lon', "Unknown")
        speed = getattr(nx, 'speed', "Unknown")
        print("Your position: lon = " + str(longitude) + ", lat = " + str(latitude)+", speed="+str(speed))

gpsd = gps(mode=WATCH_ENABLE|WATCH_NEWSTYLE)

try:
    print("Application started!")
    while running:
        getPositionData(gpsd)
        time.sleep(1.0)

except (KeyboardInterrupt):
    running = False
    print("Applications closed!")