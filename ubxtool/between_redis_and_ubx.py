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


redis_defaults = {
    'connection':'not connected',
    'rtk_source':'disabled',
    'rtk':{
        'user':'Unknown',
        'password':'Unknown',
        'server':'Unknown',
        'port':'Unknown',
        'stream':'Unknown'
    },
    'ubxtool':{
    'CFG-NAVSPG-DYNMODEL':4,
    'CFG-RATE-MEAS':100,
    'CFG-SBAS-USE_TESTMODE':1,
    'CFG-SBAS-USE_RANGING':0,
    'CFG-SBAS-PRNSCANMASK':3145760,
    'CFG-SIGNAL-SBAS_ENA':1
    },
    'gpsd':{
        'TPV':{
            'lat':None,
            'lon':None,
            'device':None,
            'mode':None,
            'altHAE':None,
            'speed':None,
            'eph':None,
            'time':None
        },
        'SKY':{
            'hdop':None
        }
    }
}

redis_connection = {'host':'127.0.0.1',
'db':1,
'password':None,
'port':6379,
'socket_timeout':None,
'decode_responses':True
}

os.system('clear') #clear the terminal (optional)

class GpsPoller(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.__flag = threading.Event() # The flag used to pause the thread
        self.__flag.set() # Set to True
        self.__running = threading.Event() # Used to stop the thread identification
        self.__running.set() # Set running to True
        self.gpsd = gps(mode=WATCH_ENABLE) #starting the stream of info

    def run(self):
        while self.__running.isSet():
            self.__flag.wait()
            try:
                report = self.gpsd.next() #this will continue to loop and grab EACH set of gpsd info to clear the buffer
            except:
                continue
            try:
                if report['class'] == 'TPV':
                    get_from_buffer('TPV', report)
                if report['class'] == 'SKY':
                    get_from_buffer('SKY', report)
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
            if os.path.exists('/dev/serial/by-id/usb-u-blox_AG_C099__ZED-F9P_DBTMNKT0-if00-port0'):
                print_flag = 1
                redis_client.set('connection', 'connected')
                start_gpsd.run()
                output = run('systemctl status gpsd').split('\n')[-2:-1]
                if len(re.findall('gpsd:ERROR: SER:', output[0]))>0:
                    #print('GPSD can\'t connect to device, restarting GPSD')
                    syslog.syslog(syslog.LOG_ERR, 'GPSD can\'t connect to device, restarting GPSD')
                    stop_gpsd.run()
                    start_gpsd.run()
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
                redis_client.set('connection','no connection')
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
    def __init__(self):
        threading.Thread.__init__(self)
        self.__flag = threading.Event()
        self.__flag.set()
        self.__running = threading.Event()
        self.__running.set()
    def run(self):
        while self.__running.isSet():# gps_thread.running:
            self.__flag.wait()
            for item in list(redis_defaults['ubxtool'].keys()):
                a = run(self.ubx_get_item(item))
                b = re.search('UBX-CFG-VALGET:\\n version \d layer \d position \d\\n  layers \(ram\)\\n    item {}/0x\d* val \d*'.format(item), a)
                try:
                    c = re.findall('val \d*', b.group(0))[0].split(' ')[1]
                except AttributeError:
                    #print('No value in {} from ubxtool'.format(item))
                    syslog.syslog(syslog.LOG_ERR, 'No value in {} from ubxtool'.format(item))
                    continue
                if int(c) != redis_defaults['ubxtool'][item]:
                    #print("Redis has changed {} from {} to {}".format(item,c,redis_defaults['ubxtool'][item]))
                    syslog.syslog(syslog.LOG_ERR, "Redis has changed {} from {} to {}".format(item,c,redis_defaults['ubxtool'][item]))
                    app = run('ubxtool -P 27.12 -z {},{}'.format(item, redis_defaults['ubxtool'][item]))
                    try:
                        if re.findall('UBX-ACK-\w*', app)[0] == 'UBX-ACK-NAK':
                            redis_defaults['ubxtool'][item] = int(c)
                            redis_client.set(item, c)
                    except IndexError:
                        redis_defaults['ubxtool'][item] = int(c) 
                        redis_client.set(item, c)
    def ubx_get_item(self, item):
        return 'ubxtool -P 27.12 -g {}'.format(item)
    def pause(self):
        self.__flag.clear()
    def resume(self):
        self.__flag.set()
    def stop(self):
        self.__flag.clear()
        self.__running.clear()
        self.join()
    

class redis_get(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.__flag = threading.Event()
        self.__flag.set()
        self.__running = threading.Event()
        self.__running.set()
    def run(self):
        while self.__running.isSet():
            self.__flag.wait()
            for item in list(redis_defaults['ubxtool'].keys()):
                if redis_client.exists(item) != 0:
                    try:
                        redis_defaults['ubxtool'][item] = int(redis_client.get(item))
                    except ValueError:
                        redis_client.set(item, redis_defaults['ubxtool'][item])
                elif redis_client.exists(item) == 0:
                    redis_client.set(item,redis_defaults['ubxtool'][item])
                #RTK_connection_params
            if redis_client.exists('rtk') != 0:
                try:
                    redis_defaults['rtk'] = redis_client.hgetall('rtk')
                except ValueError:
                    redis_client.hmset('rtk', redis_defaults['rtk'])
            elif redis_client.exists('rtk') == 0:
                redis_client.hmset('rtk', redis_defaults['rtk'])
                #RTK_source
            if redis_client.exists('rtk_source') != 0:
                try:
                    if redis_defaults['rtk_source'] != redis_client.get('rtk_source'):
                        redis_defaults['rtk_source'] = redis_client.get('rtk_source')
                        if redis_defaults['rtk_source'] == 'internet':
                            stop_gpsd.run()
                            time.sleep(4)
                            print('changing...')
                            run(r'echo GPSD_OPTIONS=\"ntrip://{}:{}@{}:{}/{}\" > /home/andrew/gpsd'.format(redis_defaults['rtk']['user'],redis_defaults['rtk']['password'],redis_defaults['rtk']['server'],redis_defaults['rtk']['port'],redis_defaults['rtk']['stream']))
                            start_gpsd.run()
                        if redis_defaults['rtk_source'] == 'disabled':
                            stop_gpsd.run()
                            print('changing...')
                            run(r'echo GPSD_OPTIONS=\"\" > /home/andrew/gpsd')
                            start_gpsd.run()
                except ValueError:
                    redis_client.set('rtk_source',redis_defaults['rtk_source']) 
            elif redis_client.exists('rtk_source') == 0:
                redis_client.set('rtk_source',redis_defaults['rtk_source'])   

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
    syslog.syslog(syslog.LOG_INFO, 'Subprocess: "' + command + '"')

    try:
        command_line_process = subprocess.Popen(
            command,
            shell = True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        process_output, _ =  command_line_process.communicate()
        syslog.syslog(syslog.LOG_DEBUG, process_output.decode('utf-8'))
    except (OSError) as exception:

        syslog.syslog(syslog.LOG_ERR, exception)
        return False
    else:
        syslog.syslog(syslog.LOG_INFO, 'Subprocess finished')

    return process_output.decode('utf-8')

def get(data, key):
    try:
        result = getattr(data, key, 'Unknown')
    except AttributeError:
        return 'Unknown'
    return result

def get_from_buffer(type, report):
    if type == "TPV":
        for field in list(redis_defaults['gpsd']['TPV'].keys()):
            result = get(report, field)
            #print(field, ": ",result)
            redis_client.set(field,str(result))
    elif type == "SKY":
        for field in list(redis_defaults['gpsd']['SKY'].keys()):
            result = get(report, field)
            #print(field, ": ",result)
            redis_client.set(field,str(result))
        satellites = get(report, 'satellites')
        sat_used = 0
        for sat in satellites:
            if sat['used']==True:
                sat_used+=1
        redis_client.set('sat_used',str(sat_used))

class start_gpsd_class():
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
    def __init__(self, *args, **kwargs):
        redis.Redis.__init__(self, *args, **kwargs)
    def set(self, a, b):
        try:
            super().set(a, b)
        except:
            syslog.syslog(syslog.LOG_ERR, 'can\'t set: "{}" in redis db'.format(a))
    def exists(self, a):
        try:
            super().exists(a)
        except:
            syslog.syslog(syslog.LOG_ERR, 'can\'t check presence of "{}"'.format(a))
    def get(self, a):
        try:
            super().get(a, b)
        except:
            syslog.syslog(syslog.LOG_ERR, 'can\'t get: "{}" in redis db'.format(a))
    def hgetall(self, a):
        try:
            super().hgetall(a)
        except:
            syslog.syslog(syslog.LOG_ERR, 'can\'t hgetall: "{}" in redis db'.format(a))
    def hmset(self, a, b):
        try:
            super().hmset(a, b)
        except:
            syslog.syslog(syslog.LOG_ERR, 'can\'t hmset: "{}" in redis db'.format(a))


if __name__ == '__main__':
<<<<<<< HEAD
    #redis_client = redis.Redis(**redis_connection) # connect to redis server
    redis_client = redis_client_class(**redis_connection)
=======
    run(r'echo GPSD_OPTIONS=\"\" > /home/andrew/gpsd')
    redis_client = redis.Redis(**redis_connection)
>>>>>>> ec09f14826c3591f32a9771d49b157811f8a713d
    stop_gpsd = stop_gpsd_class()
    start_gpsd = start_gpsd_class()
    #threads:
    redis_get_thread = redis_get()
    gps_thread = GpsPoller() # create the thread
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
   # print("Done.\nExiting.")



###############################################
