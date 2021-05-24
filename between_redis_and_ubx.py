import redis
import os
from gps import gps,WATCH_ENABLE
import time
import threading
import subprocess
import json
import re
import os
import syslog
import json

zed_f9p = '/dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00'


with open('/etc/cognitive/redis_connection_gpsd.json', 'r') as file:
    redis_connection = json.load(file)

with open('/etc/cognitive/redis_fields_gpsd.json', 'r') as file:
    redis_defaults = json.load(file)
'''
redis_defaults = {
    'connection':'not connected',  # Shows zed-f9p connection status
    'rtk_source':'disabled',       # Specify source of RTCM3 corrections 
    'rtk_connection_params':{                        # RTK connection params. This field is set as hmset (hash table)
        'user':'Unknown',
        'password':'Unknown',
        'server':'Unknown',
        'port':'Unknown',
        'stream':'Unknown'
    },
    'ubxtool':{                    # This field is not shown in redis as hmset. It gets flatten. 
    'CFG-NAVSPG-DYNMODEL':4,       # Sets dynamic platform model to automotive
    'CFG-RATE-MEAS':100,           # Sets solution output rate to 1000/value
    'CFG-SBAS-USE_TESTMODE':1,     # Enable sbas test mode 
    'CFG-SBAS-USE_RANGING':0,      # Disable using sbas for ranging 
    'CFG-SBAS-PRNSCANMASK':3145760,# SV number to listen to obtain sdcm corrections (125, 140, 141)
    'CFG-SIGNAL-SBAS_ENA':1        # Turn on SBAS
    },
    'gpsd':{                       # gpsd keys can be changed only by gpsd. This field is not shown in redis as hmset. It gets flatten. 
        'TPV':{                    # Time Position Velocity data
            'lat':None,            # Latitude
            'lon':None,            # Longitude
            'device':None,         # Device that connected to gpsd
            'mode':None,           # NMEA mode:0=Unknown,1=no fix,2=2d fix,3=3d fix
            'status':None,         # GPS fix status: 0=Unknown,1=Normal,2=DGPS,3=RTK Fixed,4=RTK Floating,5=DR,6=GNSSDR,7=Time (surveyed),8=Simulated,9=P(Y)
            'altHAE':None,         # Altitude, height above ellipsoid, in meters. Probably WGS84.
            'speed':None,          # Speed over ground, meters per second.
            'eph':None,            # Estimated horizontal Position (2D) Error in meters. Also known as Estimated Position Error (epe). Certainty unknown.
            'time':None            # Time/date stamp in ISO8601 format, UTC. May have a fractional part of up to .001sec precision. May be absent if the mode is not 2D or 3D.
        },
        'SKY':{
            'hdop':None,           # Horizontal dilution of precision, a dimensionless factor which should be multiplied by a base UERE to get a circular error estimate.
            'nSat':None,           # Number of satellite objects in "satellites" array.
            'uSat':None            # Number of satellites used in navigation solution.
        }
    }
}
'''
'''
redis_connection = {'host':'127.0.0.1',
'db':1,
'password':None,
'port':6379,
'socket_timeout':None,
'decode_responses':True
}
'''


class GpsPoller(threading.Thread):
    '''
    Obtains data from gpsd and updating redis db with those data
    '''

    def __init__(self):
        threading.Thread.__init__(self)
        self.__flag = threading.Event() # The flag used to pause the thread
        self.__flag.set() # Set to True
        self.__running = threading.Event() # Used to stop the thread identification
        self.__running.set() # Set running to True
        self.gpsd = gps(mode=WATCH_ENABLE) #starting the stream of info

    def get(self, data, key):
        try:
            result = getattr(data, key, 'Unknown')
        except AttributeError:
            return 'Unknown'
        return result

    def get_from_buffer(self, type, report):
        '''
        Updates redis database with fields defined in redis_defaults under
        'gspd' key (lat, lon, device, mode, altHAE, speed, eph, time, hdop) 
        '''
        if type == "TPV":
            for field_ in list(redis_defaults['gpsd']['TPV'].keys()):
                field = field_.split(':')[-1:][0]
                result = self.get(report, field)
                #print(field, ": ",result)
                redis_client.set(field_,str(result))
        elif type == "SKY":
            for field_ in list(redis_defaults['gpsd']['SKY'].keys()): # get HDOP
                field = field_.split(':')[-1:][0]
                sat_used = 0 #uSat
                sat_total = 0 #nSat
                #print(field, ": ",result)
                if field == 'nSat': 
                    result = self.get(report, 'satellites')
                    # calculate sattelites count that are used for solution
                    for sat in result:
                        if sat['used']==True:
                            sat_used+=1
                            sat_total+=1
                        elif sat['used']==False:
                            sat_total+=1
                    redis_client.set("GPS:statuses:satellites:nSat",str(sat_total))
                    redis_client.set("GPS:statuses:satellites:uSat",str(sat_used))
                    continue
                elif field == 'uSat':
                    continue
                result = self.get(report, field)
                redis_client.set(field_,str(result))
            

    def run(self):
        while self.__running.isSet():
            self.__flag.wait()
            try:
                report = self.gpsd.next() #this will continue to loop and grab EACH set of gpsd info to clear the buffer
            except:
                self.gpsd = gps(mode=WATCH_ENABLE) #try to connect to gpsd after service being restarted by another thread
            try:
                if report['class'] == 'TPV':
                    self.get_from_buffer('TPV', report)
                elif report['class'] == 'SKY':
                    self.get_from_buffer('SKY', report)
                elif report['class'] == 'ERROR':
                    print(report)
            except (KeyError, TypeError):
                pass
            #time.sleep(0.5) #set to whatever

    def pause(self):
        self.__flag.clear()
    def resume(self):
        self.__flag.set()
    def stop(self):
        self.__flag.clear()
        self.__running.clear()
        self.join()



class device_unplug_handler(threading.Thread):
    '''
    Stops gpsd systemd service and pauses all threads except himself
    in case of zed-f9p is not connected
    '''
    def __init__(self):
        threading.Thread.__init__(self)
        self.__flag = threading.Event() # The flag used to pause the thread
        self.__flag.set() # Set to True
        self.__running = threading.Event() # Used to stop the thread identification
        self.__running.set() # Set running to True

    def run(self):
        print_flag = 1
        while self.__running.isSet():
            self.__flag.wait()
            if os.path.exists(zed_f9p):#check whether zed-f9p is connected
                print_flag = 1
                redis_client.set('GPS:statuses:connection', 'connected')
                start_gpsd.run()
                #Check whether the gpsd systemd service started and works properly
                output = run('systemctl status gpsd').split('\n')[-2:-1]
                while len(re.findall('gpsd:ERROR: SER:', output[0]))>0:
                    #print('GPSD can\'t connect to device, restarting GPSD')
                    redis_client.set('GPS:statuses:connection','no connection')
                    syslog.syslog(syslog.LOG_ERR, 'GPSD can\'t connect to device, restarting GPSD')
                    stop_gpsd.run()
                    start_gpsd.run()
                    output = run('systemctl status gpsd').split('\n')[-2:-1]
                if 'gpsd:ERROR: ntrip' in output[0]:
                    syslog.syslog(syslog.LOG_ERR, 'Wrong RTK NTRIP params')
                    redis_client.set("GPS:statuses:RTK:errors", output[0])
                    redis_client.set('GPS:settings:RTK:rtk_source', 'disabled')
                redis_get_thread.resume()
                gps_thread.resume() # start it up
                ubx_to_redis_thread.resume()
            else:
                redis_get_thread.pause()
                gps_thread.pause() # start it up
                ubx_to_redis_thread.pause()
                if print_flag: 
                    #print('No devices connected')
                    syslog.syslog(syslog.LOG_ERR, 'No devices connected')
                    print_flag = 0
                redis_client.set('GPS:statuses:connection','no connection')
                stop_gpsd.run()
            time.sleep(1)
    def pause(self):
        self.__flag.clear()
    def resume(self):
        self.__flag.set()
    def stop(self):
        self.__flag.clear()
        self.__running.clear()
        self.join()

class ubx_to_redis(threading.Thread):
    '''
    Obtains current configuration of zef-fp9 by requesting fields from 
    key 'ubxtool' from redis_defaults dictionary. If those configurations 
    are vary from those in dictionary it chnges them in zed-f9p accordingly
    by means of ubx tool
    '''
    def __init__(self):
        threading.Thread.__init__(self)
        self.__flag = threading.Event()
        self.__flag.set()
        self.__running = threading.Event()
        self.__running.set()
    def run(self):
        while self.__running.isSet():
            self.__flag.wait()
            for item_ in list(redis_defaults['ubxtool'].keys()):
                item = item_.split(':')[-1:][0]
                a = run(self.ubx_get_item(item))
                b = re.search('UBX-CFG-VALGET:\\n version \d layer \d position \d\\n  layers \(ram\)\\n    item {}/0x\d* val \d*'.format(item), a)
                try:
                    c = re.findall('val \d*', b.group(0))[0].split(' ')[1]
                except AttributeError:
                    #print('No value in {} from ubxtool'.format(item))
                    syslog.syslog(syslog.LOG_ERR, 'No value in {} from ubxtool'.format(item))
                    continue
                if int(c) != redis_defaults['ubxtool'][item_]:
                    #print("Redis has changed {} from {} to {}".format(item,c,redis_defaults['ubxtool'][item]))
                    syslog.syslog(syslog.LOG_ERR, "Redis has changed {} from {} to {}".format(item,c,redis_defaults['ubxtool'][item_]))
                    app = run('ubxtool -P 27.12 -z {},{} 127.0.0.1:2947:{}'.format(item, redis_defaults['ubxtool'][item_], zed_f9p))
                    try:
                        if re.findall('UBX-ACK-\w*', app)[0] == 'UBX-ACK-NAK':
                            redis_defaults['ubxtool'][item_] = int(c)
                            redis_client.set(item_, c)
                    except IndexError:
                        redis_defaults['ubxtool'][item_] = int(c) 
                        redis_client.set(item_, c)
            time.sleep(1)
    def ubx_get_item(self, item):
        return 'ubxtool -P 27.12 -g {} 127.0.0.1:2947:{}'.format(item, zed_f9p)
    def pause(self):
        self.__flag.clear()
    def resume(self):
        self.__flag.set()
    def stop(self):
        self.__flag.clear()
        self.__running.clear()
        self.join()
    

class redis_get(threading.Thread):
    '''
    Gets values for 'ubxtool', 'rtk_connection_params','rtk_source' keys from 
    redis or passes defaults to redis if they doesn't exists in the database
    '''
    def __init__(self):
        threading.Thread.__init__(self)
        self.__flag = threading.Event()
        self.__flag.set()
        self.__running = threading.Event()
        self.__running.set()
    def run(self):
        redis_client.set("GPS:statuses:RTK:errors", '')
        while self.__running.isSet():
            self.__flag.wait()
            #Get values for 'ubxtool' key from redis or pass defaults to redis if they doesn't exists in database
            for item in list(redis_defaults['ubxtool'].keys()):
                if redis_client.exists(item):
                    try:
                        redis_defaults['ubxtool'][item] = int(redis_client.get(item))
                    except (ValueError, TypeError):
                        redis_client.set(item, redis_defaults['ubxtool'][item])
                else:
                    redis_client.set(item,redis_defaults['ubxtool'][item])
                #RTK_connection_params
            if redis_client.exists('GPS:settings:RTK:rtk_connection_params'):
                try:
                    redis_defaults['GPS:settings:RTK:rtk_connection_params'] = redis_client.hgetall('GPS:settings:RTK:rtk_connection_params')
                except ValueError:
                    redis_client.hmset('GPS:settings:RTK:rtk_connection_params', redis_defaults['GPS:settings:RTK:rtk_connection_params'])
            else:
                redis_client.hmset('GPS:settings:RTK:rtk_connection_params', redis_defaults['GPS:settings:RTK:rtk_connection_params'])
                #RTK_source
            if redis_client.exists('GPS:settings:RTK:rtk_source'):
                try:
                    if redis_defaults['GPS:settings:RTK:rtk_source'] != redis_client.get('GPS:settings:RTK:rtk_source'):
                        redis_defaults['GPS:settings:RTK:rtk_source'] = redis_client.get('GPS:settings:RTK:rtk_source')
                        if redis_defaults['GPS:settings:RTK:rtk_source'] == 'internet':
                            redis_client.set("GPS:statuses:RTK:errors", '')
                            print('changing...')
                            syslog.syslog(syslog.LOG_INFO,'enabling RTK via internet')
                            run('echo DEVICES="{} ntrip://{}:{}@{}:{}/{}""\n"GPSD_OPTIONS="-G -n" > /etc/default/gpsd'\
                                .format(zed_f9p,\
                                    redis_defaults['GPS:settings:RTK:rtk_connection_params']['user'],\
                                    redis_defaults['GPS:settings:RTK:rtk_connection_params']['password'],\
                                    redis_defaults['GPS:settings:RTK:rtk_connection_params']['server'],\
                                    redis_defaults['GPS:settings:RTK:rtk_connection_params']['port'],\
                                    redis_defaults['GPS:settings:RTK:rtk_connection_params']['stream']))
                            time.sleep(2)
                            gps_thread.pause() # start it up
                            ubx_to_redis_thread.pause()
                            stop_gpsd.run()
                        if redis_defaults['GPS:settings:RTK:rtk_source'] == 'disabled':
                            print('changing...')
                            syslog.syslog(syslog.LOG_INFO,'disabling RTK')
                            run(f'echo DEVICES="{zed_f9p}""\n"GPSD_OPTIONS="-G -n" > /etc/default/gpsd')
                            gps_thread.pause() # start it up
                            ubx_to_redis_thread.pause()
                            time.sleep(2)
                            stop_gpsd.run()
                except ValueError:
                    redis_client.set('GPS:settings:RTK:rtk_source',redis_defaults['GPS:settings:RTK:rtk_source']) 
            else:
                redis_client.set('GPS:settings:RTK:rtk_source',redis_defaults['GPS:settings:RTK:rtk_source'])   

            time.sleep(2)
    def pause(self):
        self.__flag.clear()
    def resume(self):
        self.__flag.set()
    def stop(self):
        self.__flag.clear()
        self.__running.clear()
        self.join()

def run(command):
    '''
    Starts subprocess and waits untill it exits. Reads stdout after subpocess completes. 
    '''
    #syslog.syslog(syslog.LOG_INFO, 'Subprocess: "' + command + '"')

    try:
        command_line_process = subprocess.Popen(
            command,
            shell = True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        process_output, _ =  command_line_process.communicate()
        #syslog.syslog(syslog.LOG_DEBUG, process_output.decode('utf-8'))
    except (OSError) as exception:

        syslog.syslog(syslog.LOG_ERR, exception)
        return False
    #else:
    #    syslog.syslog(syslog.LOG_INFO, 'Subprocess finished')

    return process_output.decode('utf-8')


#Start_gspd_class and stop_gpsd_class are workind as a light switch:
#if you've turned light off then you can't turn it once again but you can
#turn it on once. Alternativly if you turned the light on, you can't turn it on 
#again -  instead you can tun it off once. 
class start_gpsd_class():
    '''
    Starts systemd service gpsd
    '''
    def __init__(self):
        self.counter = 1
    def run(self):
        if self.counter > 0:
            print('Starting gpsd')
            syslog.syslog(syslog.LOG_INFO,'Starting GPSD')
            run(r'echo andrew | sudo -S systemctl start gpsd')
            time.sleep(2)
            self.counter = 0
            stop_gpsd.counter = 1
class stop_gpsd_class():
    '''
    Stops systemd service gpsd
    '''
    def __init__(self):
        self.counter = 1
    def run(self):
        if self.counter > 0:
            print('Stopping gpsd')
            syslog.syslog(syslog.LOG_INFO,'Stopping GPSD')
            run(r'echo andrew | sudo -S systemctl stop gpsd')
            time.sleep(2)
            self.counter = 0
            start_gpsd.counter = 1

class redis_client_class(redis.Redis):
    '''
    Class that wraps get, set, etc functions from redis libriary
    and sends logs to syslog in case of failure
    '''
    def __init__(self, *args, **kwargs):
        redis.Redis.__init__(self, *args, **kwargs)
    def set(self, a, b):
        try:
            super().set(a, b)
        except:
            syslog.syslog(syslog.LOG_ERR, 'can\'t set: "{}" in redis db'.format(a))
    def exists(self, a):
        try:
            return super().exists(a)
        except:
            syslog.syslog(syslog.LOG_ERR, 'can\'t check presence of "{}"'.format(a))
    def get(self, a):
        try:
            return super().get(a)
        except:
            syslog.syslog(syslog.LOG_ERR, 'can\'t get: "{}" in redis db'.format(a))
    def hgetall(self, a):
        try:
            return super().hgetall(a)
        except:
            syslog.syslog(syslog.LOG_ERR, 'can\'t hgetall: "{}" in redis db'.format(a))
    def hmset(self, a, b):
        try:
            super().hmset(a, b)
        except:
            syslog.syslog(syslog.LOG_ERR, 'can\'t hmset: "{}" in redis db'.format(a))


if __name__ == '__main__':
    os.system('clear') #clear the terminal (optional)
    redis_client = redis_client_class(**redis_connection)
    stop_gpsd = stop_gpsd_class()
    start_gpsd = start_gpsd_class()
    #threads:
    redis_get_thread = redis_get()
    gps_thread = GpsPoller()
    device_unplug_handler_thread = device_unplug_handler()
    ubx_to_redis_thread = ubx_to_redis()

    try:
        device_unplug_handler_thread.start()
        redis_get_thread.start()
        gps_thread.start() # start it up
        ubx_to_redis_thread.start()

    except (KeyboardInterrupt, SystemExit): #when you press ctrl+c
        print("Killing Thread...")
        redis_get_thread.stop()
        gps_thread.stop() # wait for the thread to finish what it's doing
        device_unplug_handler_thread.stop()
        ubx_to_redis_thread.stop()
        with open('/etc/cognitive/redis_fields_gpsd.json', 'w') as file:
            json.dump(redis_defaults, file)
        #run('journalctl -r -S today -u gps_handler_agro.service >\
        #     between_redis_and_ubxtool_log.txt')
   # print("Done.\nExiting.")



##########################THAT'S ALL, FOLKS!##########################
