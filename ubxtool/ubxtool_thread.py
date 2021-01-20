import re
import threading
import subprocess
import redis
redis_client = redis.Redis(host='127.0.0.1',\
                    port=6379,\
                    db=3)
def run(command):
    print(command)
    p = subprocess.Popen(command, shell = True, stdout = subprocess.PIPE)
    (output, err) = p.communicate()
    p_status =  p.wait()
    print(output.decode('utf-8'))
    return output

class ubx_to_redis(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
    def run(self):
        while True:# gps_thread.running:
            items = ['CFG-NAVSPG-DYNMODEL',\
                        'CFG-RATE-MEAS',\
                        'CFG-SBAS-USE_TESTMODE',\
                        'CFG-SBAS-USE_RANGING',\
                        'CFG-SBAS-PRNSCANMASK',\
                        'CFG-SIGNAL-SBAS_ENA']
            for item in items:
                print('\n',item, '\n')
                a = run(self.ubx_get_item(item))
                b = re.findall('UBX-CFG-VALGET:\\n version \d layer \d position \d\\n  layers \(\w*\)\\n    item {}/0x\d* val \d*'.format(item), a.decode('utf-8'))
                for c in b:
                    redis_client.hset(item, re.findall('layers \(\w*\)',  c)[0],re.findall('val \d*', c)[0])
    def ubx_get_item(self, item):
        return 'ubxtool -P 27.12 -g {}'.format(item)

ubx_to_redis_thread = ubx_to_redis()
ubx_to_redis_thread.start()