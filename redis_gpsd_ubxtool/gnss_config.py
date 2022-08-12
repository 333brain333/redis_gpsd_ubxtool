# pylint: disable=import-error
# pylint: disable=too-many-instance-attributes

'''
Configures ZED-F9P with Redis
'''
from time import sleep
import threading
import subprocess
from enum import Enum
import logging
from logging.handlers import RotatingFileHandler
import json
import re
import syslog
from pathlib import Path
from gps import gps,WATCH_ENABLE
import redis
from setqueue import OrderedSetPriorityQueue
from health_reporter import Error, ErrorType, ErrorSource, HealthReporter

ZED_F9P = '/dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00'

with open(Path(__file__).parent / Path('redis_connection_settings.json'), 'r') as file:
    redis_connection_settings = json.load(file)


class ErrCode(Enum):
    """
    Коды ошибок
    """
    NAVRTK011_NO_GPSD                         = (11, "RTK: no gpsd running")

    def __init__(self, id, text):
        self.text = text
        self.err_id = id

class LogLog():
    '''
    Log into syslog and into file
    '''
    def __init__(self):
        log_formatter = logging.Formatter(
                '%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s'
                )
        log_file = f'{str(Path(__file__).parent.resolve())}/gnss_config.log'
        my_handler = RotatingFileHandler(
                log_file, mode='a', maxBytes=5*1024*1024,
                backupCount=2, encoding=None, delay=False
                )
        my_handler.setFormatter(log_formatter)
        my_handler.setLevel(logging.DEBUG)
        self.app_log = logging.getLogger('root')
        self.app_log.setLevel(logging.DEBUG)
        self.app_log.addHandler(my_handler)

    def info(self, text:str)->None:
        '''
        Info level loging into a file and the syslog
        '''
        print(text)
        self.app_log.info(text)
        syslog.syslog(syslog.LOG_INFO, text)

    def error(self, text:str)->None:
        '''
        Error level loging into a file and the syslog
        '''
        print(text)
        self.app_log.error(text)
        syslog.syslog(syslog.LOG_ERR, text)

def run(command:str):
    '''
    Starts subprocess and waits untill it exits. Reads stdout after subpocess completes.
    '''
    try:
        command_line_process = subprocess.Popen(
            command,
            shell = True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        process_output, _ =  command_line_process.communicate()
    except (OSError) as exception:
        logger.error(f'run error {exception}')
        return False
    return process_output.decode('utf-8')

class GpsPoller(threading.Thread):

    '''
    Obtains data from gpsd and updating redis db with those data
    '''

    def __init__(self, log_log: LogLog):
        threading.Thread.__init__(self, name='GPSD_poller')
        self.log_log = log_log
        self.__flag = threading.Event() # The flag used to pause the thread
        self.__flag.set() # Set to True
        self.__running = threading.Event() # Used to stop the thread identification
        self.__running.set() # Set running to True
        #starting the stream of info from gpsd in json format
        while True:
            try:
                self.gpsd = gps(mode=WATCH_ENABLE)
                break
            except ConnectionRefusedError:
                self.log_log.error("gpsd_poller: no gpsd running")
            sleep(1) #starting the stream of info

    @classmethod
    def get_from_buffer(cls, msg_type, report):
        '''
        Updates a redis database with fields defined in the redis_defaults under
        'gspd' key (lat, lon, device, mode, altHAE, speed, eph, time, hdop)
        '''
        if msg_type == "TPV":
            for field_ in list(redis_defaults['gpsd']['TPV'].keys()):
                field = field_.split(':')[-1:][0]
                result = getattr(report, field, 'Unknown')
                redis_client.set(field_,str(result))
        elif msg_type == "SKY":
            for field_ in list(redis_defaults['gpsd']['SKY'].keys()): # get HDOP
                field = field_.split(':')[-1:][0]
                result = getattr(report, field, 'Unknown')
                redis_client.set(field_,str(result))

    def run(self):
        while self.__running.isSet():
            self.__flag.wait()
            try:
                #this will continue to loop and grab EACH set of gpsd info to clear the buffer
                report = self.gpsd.next()
            except (StopIteration,ConnectionResetError):
                #try to connect to gpsd after service being restarted by another thread
                while True:
                    try:
                        #starting the stream of info
                        self.gpsd = gps(mode=WATCH_ENABLE)
                        break
                    except ConnectionRefusedError:
                        self.log_log.error("gpsd_poller: no gpsd running")
                    sleep(1)
            try:
                if report['class'] == 'TPV':
                    self.get_from_buffer('TPV', report)
                elif report['class'] == 'SKY':
                    self.get_from_buffer('SKY', report)
                elif report['class'] == 'ERROR':
                    self.log_log.error(report['message'])
            except (KeyError, TypeError):
                pass
            #sleep(0.5) #set to whatever

    def pause(self):
        'pauses the thread'
        self.__flag.clear()
    def resume(self):
        'resumes the paused thread'
        self.__flag.set()
    def stop(self):
        'stops the thread'
        self.__flag.clear()
        self.__running.clear()
        self.join()


class WatchDog(threading.Thread):
    '''
    Stops gpsd systemd service and pauses all threads except himself
    in case of zed-f9p is not connected
    '''
    def __init__(self, log_log: LogLog):
        threading.Thread.__init__(self, name='WatchDog')
        self.log_log = log_log
        self.__flag = threading.Event() # The flag used to pause the thread
        self.__flag.set() # Set to True
        self.__running = threading.Event() # Used to stop the thread identification
        self.__running.set() # Set running to True

    def run(self):
        while self.__running.isSet():
            self.__flag.wait()
            #Check whether the gpsd systemd service started and works properly
            #gpsd:ERROR: response: {"class":"ERROR","message":"Can't open
            if not ubxtool.check_gpsd_connection():
                self.log_log.error('Watchdog: no connection to GNSS module')
                stop_gpsd.run()
                start_gpsd.run()
                sleep(1)
            sleep(1)

    def pause(self):
        self.__flag.clear()
    def resume(self):
        self.__flag.set()
    def stop(self):
        self.__flag.clear()
        self.__running.clear()
        self.join()

class Ubxtool():
    '''
    Configures zed-f9p with a given command
    and checks the "ACK-ACK" message presense in an
    output
    '''

    def __init__(self, log_log: LogLog, err_que: OrderedSetPriorityQueue) -> None:
        self.log_log = log_log
        self.err_que = err_que

    def check_gpsd_connection(self)->bool:
        '''
        Returns true if gpsd is attached to the GNSS module
        '''
        if self.set('CFG-UART1-BAUDRATE','115200'):
            return True
        return False

    def get(self, pos: str)->bool:
        '''
        Obtains value on the RAM layer of the given position
        '''
        while True:
            result = run(f'ubxtool -g {pos} 127.0.0.1:2947:{ZED_F9P}').split('\n\n')
            for out in result:
                if 'UBX-CFG-VALGET' in out\
                    and 'layers (ram)' in out\
                    and pos in out:
                    return out.split()[-1:][0]
                if 'no devices attached' in out:
                    self.log_log.error(f"{pos} FAIL. No devices attached")
                    return False
                if 'Connection refused' in out:
                    self.log_log.error('ubxtool: no gpsd running')
                    self.err_que.insert(ErrCode.NAVRTK011_NO_GPSD.name)
                sleep(1)

    def set(self, pos: str, value: int)->bool:
        '''
        Sets value by its position
        '''
        while True:
            out = run(f'ubxtool -z {pos},{value} 127.0.0.1:2947:{ZED_F9P}')
            if 'UBX-ACK-ACK' in out:
                return True
            if 'UBX-ACK-NAK' in out:
                self.log_log.error(f"{pos},{value} FAIL")
                return False
            if 'no devices attached' in out:
                self.log_log.error(f"{pos} FAIL. No devices attached")
                return False
            if 'Connection refused' in out:
                self.log_log.error('ubxtool: no gpsd running')
                self.err_que.insert(ErrCode.NAVRTK011_NO_GPSD.name)
            sleep(1)


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
                b = re.search('UBX-CFG-VALGET:\\n version \d layer \d reserved 0,0\\n  layers \(ram\)\\n    item {}/0x\d* val \d*'.format(item), a)
                try:
                    c = re.findall('val \d*', b.group(0))[0].split(' ')[1]
                except AttributeError:
                    #print('No value in {} from ubxtool'.format(item))
                    syslog.syslog(syslog.LOG_ERR, 'No value in {} from ubxtool'.format(item))
                    continue
                if int(c) != redis_defaults['ubxtool'][item_]:
                    #print("Redis has changed {} from {} to {}".format(item,c,redis_defaults['ubxtool'][item_]))
                    syslog.syslog(syslog.LOG_ERR, "Redis has changed {} from {} to {}".format(item,c,redis_defaults['ubxtool'][item_]))
                    app = run('ubxtool -P 27.12 -z {},{} 127.0.0.1:2947:{}'.format(item, redis_defaults['ubxtool'][item_], ZED_F9P))
                    try:
                        if re.findall('UBX-ACK-\w*', app)[0] == 'UBX-ACK-NAK':
                            redis_defaults['ubxtool'][item_] = int(c)
                            redis_client.set(item_, c)
                    except IndexError:
                        redis_defaults['ubxtool'][item_] = int(c) 
                        redis_client.set(item_, c)
            sleep(1)

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
    Gets values for 'ubxtool' keys from 
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

            sleep(2)
    def pause(self):
        self.__flag.clear()
    def resume(self):
        self.__flag.set()
    def stop(self):
        self.__flag.clear()
        self.__running.clear()
        self.join()

#Start_gspd_class and stop_gpsd_class are workind as a light switch:
#if you've turned light off then you can't turn it once again but you can
#turn it on once. Alternativly if you turned the light on, you can't turn it on 
#again -  instead you can turn it off once. 
class StartGpsd():
    '''
    Starts systemd service cgn_gpsd.service
    '''
    def __init__(self, log_log: LogLog):
        self.log_log = log_log
        self.counter = 1
    def run(self):
        '''
        Starts cgn_gpsd.service
        '''
        if self.counter > 0:
            self.log_log.info('Starting cgn_gpsd.service')
            run('systemctl start cgn_gpsd.socket')
            sleep(2)
            self.counter = 0
            stop_gpsd.counter = 1

class StopGpsd():
    '''
    Stops systemd service cgn_gpsd.service
    '''
    def __init__(self, log_log: LogLog):
        self.log_log = log_log
        self.counter = 1
    def run(self):
        '''
        Stops cgn_gpsd.service
        '''
        if self.counter > 0:
            self.log_log.info('Stopping cgn_gpsd.service')
            run('pkill -9 gpsd && systemctl stop cgn_gpsd.service cgn_gpsd.socket')
            sleep(2)
            self.counter = 0
            start_gpsd.counter = 1

class ErrReportClass(threading.Thread):
    '''
    Health reporter class. Obtains an error from the
    queue and sends keepalives.
    '''
    def __init__(self,
    err_queue: OrderedSetPriorityQueue,
    log_log: LogLog,
    redis_host='192.168.10.208',
    redis_port=6379) -> None:
        threading.Thread.__init__(self, daemon=True, name="ErrReport")
        self.log_log = log_log
        self._redis_host = redis_host
        self._redis_port = redis_port
        self._msg_type = ErrorType.error
        self._msg_source = ErrorSource.GPSservice
        self._error_sender = HealthReporter(self._msg_source, self._redis_host, self._redis_port)
        self._cycle_time = self._error_sender.getKeepaliveCycleTimeSec()
        self._err_queue = err_queue
    def run(self)->None:
        while True:
            # т.к. служба может стартануть раньше редиса,
            # ожидаем его готовности
            if self._error_sender.isConnected():
                break
            sleep(1)
        if not self._error_sender.initConfig():
            self.log_log.error("Failed to init healthReporter config from Redis")
            return False
        while True:
            # если условие не выполняется -
            # система в целом еще не сконфигурирована
            # например, не все устройства подключены,
            # или не указаны необходимые устройства
            # поэтому не нужно рапортовать об ошибках
            if self._error_sender.isRedisConfigReady():
                #print("ready")
                break
            sleep(1)
        # cycle to check health
        # active errors should be reported
        # not less frequently than cycleTime
        while True:
            if self._error_sender.isConnected():
                sleep(3)
                try:
                    err_code = self._err_queue.pop()
                    err = Error(self._msg_source, self._msg_type, err_code)
                    self._error_sender.pushError(err)
                    #print("spin")
                except IndexError:
                    pass
                if self._error_sender.getSecondsToNextKeepalive() < 0:
                    self._error_sender.keepalive()
            else:
                sleep(3)
                self._error_sender = HealthReporter(
                    self._msg_source, self._redis_host, self._redis_port)
                self._cycle_time = self._error_sender.getKeepaliveCycleTimeSec()


if __name__ == '__main__':
    logger = LogLog()
    err_que = OrderedSetPriorityQueue(maxlen = len(ErrCode))
    err_report = ErrReportClass(err_que, logger, redis_host=REDIS_HOST)
    while True:
        try:
            redis_client = redis.StrictRedis(**redis_connection)
            break
        except redis.exceptions.ConnectionError:
            logger.error(f"couldn't connect to the redis server {REDIS_HOST}")
            sleep(1)
    stop_gpsd = StopGpsd(logger)
    start_gpsd = StartGpsd(logger)
    ubxtool = Ubxtool(logger, err_que)
    #threads:
    redis_get_thread = redis_get()
    gps_poller = GpsPoller(logger)
    watchdog = WatchDog(logger)
    ubx_to_redis_thread = ubx_to_redis()

    try:
        watchdog.start()
        redis_get_thread.start()
        gps_poller.start() # start it up
        ubx_to_redis_thread.start()

    except (KeyboardInterrupt, SystemExit): #when you press ctrl+c
        print("Killing Thread...")
        redis_get_thread.stop()
        gps_poller.stop() # wait for the thread to finish what it's doing
        watchdog.stop()
        ubx_to_redis_thread.stop()
        with open(Path(__file__).parent / Path('redis_fields_gpsd.json'), 'w') as file:
            json.dump(redis_defaults, file)
        #run('journalctl -r -S today -u gps_handler_agro.service >\
        #     between_redis_and_ubxtool_log.txt')
   # print("Done.\nExiting.")



##########################THAT'S ALL, FOLKS!##########################
