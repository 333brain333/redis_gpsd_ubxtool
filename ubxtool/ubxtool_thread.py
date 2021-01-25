import re
import threading
import subprocess
import time
import redis
redis_client = redis.Redis(host='127.0.0.1',\
                    port=6379,\
                    db=0)
redis_defaults = {
    'connection':'not connected',
    'rtk_source':'disabled',
    'rtk':{``
        'user':None,
        'password':None,
        'server':None,
        'port':None,
        'stream':None
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
            'status':None,
            'altHAE':None,
            'speed':None,
            'eph':None
        },
        'SKY':{
            'hdop':None
        }
    }
}


def run(command):
    print(command)
    p = subprocess.Popen(command, shell = True, stdout = subprocess.PIPE)
    (output, err) = p.communicate()
    p_status =  p.wait()
    #print(output.decode('utf-8'))
    return output

class redis_get(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
    def run(self):
        while True:
            for item in list(redis_defaults['ubxtool'].keys()):
                if redis_client.exists(item) != 0:
                    redis_defaults['ubxtool'][item] = int(redis_client.get(item))
                elif redis_client.exists(item) == 0:
                    redis_client.set(item,redis_defaults['ubxtool'][item])
            time.sleep(2)

class ubx_to_redis(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
    def run(self):
        while True:# gps_thread.running:
            for item in list(redis_defaults['ubxtool'].keys()):
                a = run(self.ubx_get_item(item))
                b = re.search('UBX-CFG-VALGET:\\n version \d layer \d position \d\\n  layers \(ram\)\\n    item {}/0x\d* val \d*'.format(item), a.decode('utf-8'))
                try:
                    c = re.findall('val \d*', b.group(0))[0].split(' ')[1]
                except AttributeError:
                    print('\n EXCEPTION',a,'\n')
                    continue
                if int(c) != redis_defaults['ubxtool'][item]:
                    print(c, '<--!=-->',redis_defaults['ubxtool'][item])
                    run('ubxtool -P 27.12 -z {},{}'.format(item, redis_defaults['ubxtool'][item]))
    def ubx_get_item(self, item):
        return 'ubxtool -P 27.12 -g {}'.format(item)

ubx_to_redis_thread = ubx_to_redis()
redis_get_thread = redis_get()
try:
    ubx_to_redis_thread.start()
    redis_get_thread.start()
except KeyboardInterrupt:
    ubx_to_redis_thread.join()
    redis_get_thread.join()