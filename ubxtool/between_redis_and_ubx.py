import redis
import os
from gps import *
import time
import threading
import subprocess
import json
import re


gpsd = None #seting the global variablecute
report = None
satellites = None
fields_TPV = ['lat',\
        'lon',\
        'device',\
        'mode',\
        'status',\
        'altHAE',\
        'speed',\
        'eph',]
fields_SKY = ['hdop']

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

class device_unplug_handler(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
    def run(self):
        while gps_thread.running:
            a = subprocess.run('ls /dev/serial/by-id',shell = True, stdout=subprocess.PIPE)
            try:
                re.search('usb-u-blox_AG_C099__ZED-F9P_DBTMNKT0-if00-port0', a.stdout.decode('utf-8')).group(0)
                redis_client.set('connection', 'connected')
            except AttributeError:
                print('No devices connected')
                redis_client.set('connection','no connection')
                restart_gpsd()
            time.sleep(0.2)


def get_from_buffer(type):
    global satellites
    if type == "TPV":
        for field in fields_TPV:
            result = getattr(report, field, 'Unknown')
            #print(field, ": ",result)
            redis_client.set(field,str(result))
    elif type == "SKY":
        for field in fields_SKY:
            result = getattr(report, field, 'Unknown')
            #print(field, ": ",result)
            redis_client.set(field,str(result))
        satellites = getattr(report, 'satellites')
        sat_used = 0
        for sat in satellites:
            if sat['used']==True:
                sat_used+=1
        redis_client.set('sat_used',str(sat_used))

def restart_gpsd():
    print('Stopping gpsd')
    subprocess.run('echo andrew | sudo -S systemctl stop gpsd',\
            shell = True, check =True)
    time.sleep(5)
    print('Starting gpsd')
    subprocess.run('echo andrew | sudo -S systemctl start gpsd',\
            shell = True, check =True)


if __name__ == '__main__':
    redis_client = redis.Redis(host=host_ip,\
                     password=user_password,\
                     port=host_port,\
                     socket_timeout=s_t,\
                     db=database)
    gps_thread = GpsPoller() # create the thread
    device_unplug_handler_thread = device_unplug_handler()
    try:
        gps_thread.start() # start it up
        device_unplug_handler_thread.start()
        while True:
        #It may take a second or two to get good data
        #print gpsd.fix.latitude,', ',gpsd.fix.longitude,'  Time: ',gpsd.utc
            try:
                if report['class'] == 'TPV':
                    get_from_buffer('TPV')
                if report['class'] == 'SKY':
                    get_from_buffer('SKY')
            except (KeyError, TypeError):
                pass
            time.sleep(0.5) #set to whatever

    except (KeyboardInterrupt, SystemExit): #when you press ctrl+c
        print("\nKilling Thread...")
        gps_thread.running = False
        gps_thread.join() # wait for the thread to finish what it's doing
        device_unplug_handler_thread.join()
    print("Done.\nExiting.")




    import re
def run(command):
    p = subprocess.Popen(command, shell = True, stdout = subprocess.PIPE)
    (output, err) = p.communicate()
    p_status =  p.wait()
    #print(output)
    return output

def make_ubx_bet_cmd(item):
    return 'ubxtool -P 27.12 -g {}'.format(item)

items = ['CFG-NAVSPG-DYNMODEL',\
            'CFG-RATE-MEAS',\
            'CFG-SBAS-USE_TESTMODE',\
            'CFG-SBAS-USE_RANGING',\
            'CFG-SBAS-PRNSCANMASK',\
            'CFG-SIGNAL-SBAS_ENA',
            '']
for item in items:
    print('\n',item, '\n')
    a = run(make_ubx_bet_cmd(item))
    print(re.findall('val \d*', a.decode('utf-8')))

