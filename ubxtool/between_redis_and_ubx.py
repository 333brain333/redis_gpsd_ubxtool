import redis
import os
from gps import *
from time import *
import time
import threading


gpsd = None #seting the global variable
report = None
host_ip = '127.0.0.1'
database = 1
user_name = None
user_password = None
host_port = 6379
s_t = None
os.system('clear') #clear the terminal (optional)

class GpsPoller(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        global gpsd #bring it in scope
        gpsd = gps(mode=WATCH_ENABLE) #starting the stream of info
        self.current_value = None
        self.running = True #setting the thread running to true

    def run(self):
        global gpsd
        global report
        while gps_thread.running:
            report = gpsd.next() #this will continue to loop and grab EACH set of gpsd info to clear the buffer


if __name__ == '__main__':
    redis_client = redis.Redis(host=host_ip,\
                     password=user_password,\
                     port=host_port,\
                     socket_timeout=s_t,\
                     db=database)
    gps_thread = GpsPoller() # create the thread
    try:
        gps_thread.start() # start it up
        while True:
        #It may take a second or two to get good data
        #print gpsd.fix.latitude,', ',gpsd.fix.longitude,'  Time: ',gpsd.utc
            try:
                if report['class'] == 'TPV':
                    lat = getattr(report, 'lat', 'Unknown')
                    lon = getattr(report, 'lon', 'Unknown')
                    dev = getattr(report, 'device', 'Unknown')
                    print("Device: ", dev, "Your position: lon = " + str(lon) + ", lat = " + str(lat))
                    redis_client.mset({"longitude: ":str(lon), "latitude: ":str(lat),"device: ":str(dev)})
            except KeyError:
                time.sleep(5)
            time.sleep(5) #set to whatever

    except (KeyboardInterrupt, SystemExit): #when you press ctrl+c
        print("\nKilling Thread...")
        gps_thread.running = False
        gps_thread.join() # wait for the thread to finish what it's doing
    print("Done.\nExiting.")

