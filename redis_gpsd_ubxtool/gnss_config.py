# pylint: disable=import-error
# pylint: disable=too-many-instance-attributes

'''
Configures ZED-F9P with Redis
'''
from time import sleep
import threading
import os
import subprocess
from enum import Enum
import logging
from logging.handlers import RotatingFileHandler
import json
import signal
import syslog
from pathlib import Path
from gps import gps,WATCH_ENABLE
import redis
from setqueue import OrderedSetPriorityQueue
from health_reporter import Error, ErrorType, ErrorSource, HealthReporter
    
ZED_F9P = '/dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00'
with open(Path(__file__).parent / Path('redis_connection_settings.json'), 'r') as file:
    REDIS_CONNECTION_SETTINGS = json.load(file)


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


class GracefulKiller:
    '''
    Returns true if programm main process was interrupted
    '''
    kill_now = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args):
        self.kill_now = True


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

class GnssStatuses(threading.Thread):

    '''
    Obtains data from gpsd and updating redis db with those data
    '''

    def __init__(self, log_log: LogLog):
        threading.Thread.__init__(self, name='GPSD_poller', daemon=True)
        self.log_log = log_log
        #starting the stream of info from gpsd in json format
        while True:
            try:
                self.gpsd = gps(mode=WATCH_ENABLE)
                break
            except ConnectionRefusedError:
                self.log_log.error("gpsd_poller: no gpsd running")
            sleep(1) #starting the stream of info

    @classmethod
    def get_from_buffer(cls, report):
        '''
        Updates a redis database with fields defined in the redis_defaults under
        'gspd' key (lat, lon, device, mode, altHAE, speed, eph, time, hdop)
        '''
        for key in redis_client.keys('GPS:statuses:*'):
            field = key.replace('GPS:statuses:','')
            value = getattr(report, field, 'Unknown')
            redis_client.set(field, str(value))

    def run(self):
        while True:
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
                    self.get_from_buffer(report)
                elif report['class'] == 'SKY':
                    self.get_from_buffer(report)
                elif report['class'] == 'ERROR':
                    self.log_log.error(report['message'])
            except (KeyError, TypeError):
                pass
            #sleep(0.5) #set to whatever


class WatchDog(threading.Thread):
    '''
    Stops gpsd systemd service and pauses all threads except himself
    in case of zed-f9p is not connected
    '''
    def __init__(self, log_log: LogLog):
        threading.Thread.__init__(self, name='WatchDog')
        self.log_log = log_log

    def run(self):
        while not killer.kill_now:
            #Check whether the gpsd systemd service started and works properly
            #gpsd:ERROR: response: {"class":"ERROR","message":"Can't open
            if not ubxtool.check_gpsd_connection():
                self.log_log.error('Watchdog: no connection to GNSS module')
                stop_gpsd.run()
                start_gpsd.run()
                sleep(1)
            sleep(1)


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


class GnssSettings(threading.Thread):
    '''
    Obtains current configuration of zef-fp9 by requesting fields from 
    key 'ubxtool' from redis_defaults dictionary. If those configurations 
    are vary from those in dictionary it chnges them in zed-f9p accordingly
    by means of ubx tool
    '''
    def __init__(self, log_log: LogLog):
        threading.Thread.__init__(self, daemon=True, name='GnssSettings')
        self.log_log = log_log
    def run(self):
        while True:
            for redis_field in redis_client.keys('GPS:statuses:*'):
                if not "RTK" in redis_field:
                    redis_value = redis_client.get(redis_field)
                    try:
                        if zedf9p_current_config[redis_field] != redis_value:
                            self.log_log.info(f'{redis_field},{redis_value}->ublox')
                            ubxtool.set(redis_field, int(redis_value))
                    except KeyError:
                        zedf9p_current_config[redis_field] = redis_value
                        ubxtool.set(redis_field, redis_value)
                    redis_value = redis_client.get(redis_field)
            sleep(1)


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
    try:
        killer = GracefulKiller()
        zedf9p_current_config: dict = {}
        logger = LogLog()
        err_que = OrderedSetPriorityQueue(maxlen = len(ErrCode))
        err_report = ErrReportClass(err_que, logger, redis_host=REDIS_CONNECTION_SETTINGS['host'])
        while True:
            try:
                redis_client = redis.StrictRedis(decode_responses=True, **REDIS_CONNECTION_SETTINGS)
                break
            except redis.exceptions.ConnectionError:
                logger.error(
                    f"couldn't connect to the redis server {REDIS_CONNECTION_SETTINGS['host']}")
                sleep(1)
        stop_gpsd = StopGpsd(logger)
        start_gpsd = StartGpsd(logger)
        ubxtool = Ubxtool(logger, err_que)

        #threads:
        gnss_statuses = GnssStatuses(logger)
        watchdog = WatchDog(logger)
        gnss_settings = GnssSettings(logger)

        watchdog.start()
        gnss_statuses.start() # start it up
        gnss_settings.start()

    except (KeyboardInterrupt, SystemExit):
        logger.info("Finished running gnss_config...")
        gnss_statuses.stop() # wait for the thread to finish what it's doing
        watchdog.stop()
        gnss_settings.stop()
        os._exit(0)
