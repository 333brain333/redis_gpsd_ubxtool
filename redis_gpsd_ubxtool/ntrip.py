# pylint: disable=protected-access
# pylint: disable=too-many-instance-attributes
# pylint: disable=redefined-builtin
'''
Runs ntripclient
'''
import subprocess
from pathlib import Path
import syslog
import logging
from logging.handlers import RotatingFileHandler
import os
from threading import Thread, Event
from enum import Enum
import signal
from time import sleep, time
import argparse
from gps import gps,WATCH_ENABLE
from ntrip_config import REDIS_HOST
from setqueue import OrderedSetPriorityQueue
from health_reporter import Error, ErrorType, ErrorSource, HealthReporter



class ErrCode(Enum):
    """
    Коды ошибок
    """
    NAVRTK001_SERVICE_UNAVAILABLE             = (1, "RTK: no such name of the base station")
    NAVRTK002_UNAUTHORIZED                    = (2, "RTK: wrong login/password")
    NAVRTK003_TIMEOUT_MSG                     = (
        3, "RTK: no corrections"
        )
    NAVRTK004_TIMEOUT                         = (
        4, "RTK: no corrections"
        )
    NAVRTK005_NO_DGPSAGE                      = (5, "RTK: no corrections")
    NAVRTK006_UNKNOWN_ERROR                   = (6, "RTK: unknown error")
    NAVRTK007_NETW_UNREACH                    = (7, "RTK: сelluar network unreachable")
    NAVRTK008_TWO_CONN_SIMULT                 = (8, \
        "RTK: login is already in use")
    NAVRTK009_WRONG_PORT                      = (9, "RTK: wrong port")
    NAVRTK010_WRONG_SERVER                    = (10, "RTK: wrong server name")
    NAVRTK011_NO_GPSD                         = (11, "RTK: no gpsd running")

    def __init__(self, id, text):
        self.text = text
        self.err_id = id

class GracefulKiller:
  kill_now = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self, *args):
    self.kill_now = True

class LogLog():
    '''
    Log into syslog and into file
    '''
    def __init__(self):
        log_formatter = logging.Formatter(
                '%(asctime)s %(levelname)s %(funcName)s(%(lineno)d) %(message)s'
                )
        log_file = f'{str(Path(__file__).parent.resolve())}/ntrip.log'
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

class ErrReportClass(Thread):
    '''
    Health reporter class. Obtains an error from the
    queue and sends keepalives.
    '''
    def __init__(self,
    err_queue: OrderedSetPriorityQueue,
    log_log: LogLog,
    redis_host='192.168.10.208',
    redis_port=6379) -> None:
        Thread.__init__(self, daemon=True, name="ErrReport")
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
                    if err_code in (ErrCode.NAVRTK004_TIMEOUT.name,
                    ErrCode.NAVRTK005_NO_DGPSAGE.name):
                        watch_dog.resume()
                    else:
                        start_ntrip.resume()
                    #print("spin")
                except IndexError:
                    pass
                if self._error_sender.getSecondsToNextKeepalive() < 0:
                    self._error_sender.keepalive()
            else:
                sleep(3)
                self._error_sender = HealthReporter(
                    self._msg_source, self._redis_host, self._redis_port
                    )
                self._cycle_time = self._error_sender.getKeepaliveCycleTimeSec()


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


def run_iter(cmd:str):
    '''
    Runs subprocess and prints outut as soon as a process gives it
    '''
    popen = subprocess.Popen(cmd,
    shell=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True)
    #print(cmd)
    while True:
        try:
            for stdout_line in iter(popen.stdout.readline, ""):
                yield stdout_line
        except UnicodeDecodeError:
            continue
        popen.stdout.close()
        return_code = popen.wait()
        if return_code != -15:
            logger.error(f'run iter ERROR: {return_code} {cmd}')
            raise subprocess.CalledProcessError(return_code, cmd)

def config_zedf9p(cmd:str, log_log: LogLog)->None:
    '''
    Configures zed-f9p with a given command
    and checks the "ACK-ACK" message presense in an
    output
    '''
    while True:
        try:
            #starting the stream of info
            gps(mode=WATCH_ENABLE)
            break
        except ConnectionRefusedError:
            log_log.error("Config: no gpsd running")
            err_que.insert(ErrCode.NAVRTK011_NO_GPSD.name)
        sleep(1)
    out = run(cmd)
    if 'UBX-ACK-ACK' in out:
        log_log.info("baudrate configuration successfull")
    else:
        log_log.error("baudrate configuration FAIL")


class StartNtrip(Thread):
    '''
    Starts ntripclient and checks output for a issues
    '''
    def __init__(self, err_queue: OrderedSetPriorityQueue, log_log: LogLog, **kwrags):
        Thread.__init__(self, daemon=True, name="ntripclient_thread")
        self.err_queue = err_queue
        self.__flag = Event()
        self.__flag.set()
        self.log_log = log_log
        self.args_dict = args
    def run(self):
        '''
        Main loop
        '''
        start_ntrip_cmd = \
            f'{str(Path(__file__).parent.resolve() / Path("./ntripclient/bin/ntripclient"))} \
                -s {self.args_dict.server} \
                -m {self.args_dict.stream} \
                -r {self.args_dict.port} \
                -u {self.args_dict.username} \
                -p {self.args_dict.password} \
                -D /dev/ttyS4 -B 115200'
        for stdout_line in run_iter(start_ntrip_cmd):
            #print(start_ntrip_cmd)
            #print("STDOUT: ",stdout_line )
            #no such base station
            if "Could not get the requested data: HTTP/1.1 404 Not Found"\
                 in stdout_line:
                self.log_log.error(f"No such base station: >{self.args_dict.stream}<")
                self.err_queue.insert(ErrCode.NAVRTK001_SERVICE_UNAVAILABLE.name)
                self.__flag.clear()
                self.__flag.wait()
                os._exit(0)
            #wrong username or passwd
            if "Could not get the requested data: HTTP/1.1 401 Unauthorized"\
                 in stdout_line:
                self.log_log.error(
                f"Wrong username/password: >{self.args_dict.username}</>{self.args_dict.password}<")
                self.err_queue.insert(ErrCode.NAVRTK002_UNAUTHORIZED.name)
                self.__flag.clear()
                self.__flag.wait()
                os._exit(0)
            #either internet loss in the process or wrong server
            if "ERROR: more than 120 seconds no activity" in\
                 stdout_line:
                self.log_log.error("ERROR: more than 120 seconds no activity")
                self.err_queue.insert(ErrCode.NAVRTK003_TIMEOUT_MSG.name)
                self.__flag.clear()
                self.__flag.wait()
                os._exit(0)
            #no connection to the internet
            if "connect: Network is unreachable" in stdout_line:
                self.log_log.error("connect: Network is unreachable")
                self.err_queue.insert(ErrCode.NAVRTK007_NETW_UNREACH.name)
                self.__flag.clear()
                self.__flag.wait()
                os._exit(1)
            #attempt to connect more than two users with a same login
            if "Could not get the requested data: HTTP/1.1 503 Service Unavailable"\
                    in stdout_line:
                self.log_log.error(
                        "Could not get the requested data: HTTP/1.1 503 Service Unavailable"
                            )
                self.log_log.error("Ntrip login is already in use")
                self.err_queue.insert(ErrCode.NAVRTK008_TWO_CONN_SIMULT.name)
                self.__flag.clear()
                self.__flag.wait()
                os._exit(0)
            #wrong port
            if "Could not get the requested data: HTTP/1.1 301 Moved Permanently" in stdout_line\
                      or 'Could not get the requested data: 220 FTP Server ready' in stdout_line\
                                                 or 'connect: Connection refused' in stdout_line:
                self.log_log.error(f"Wrong port: >{self.args_dict.port}<")
                self.err_queue.insert(ErrCode.NAVRTK009_WRONG_PORT.name)
                self.__flag.clear()
                self.__flag.wait()
                os._exit(0)
            #attempt to connect more than two users
            if "Server name lookup failed for"\
                    in stdout_line:
                self.log_log.error(
                        "Server name lookup failed for"
                            )
                self.log_log.error(f"Wrong server name: >{self.args_dict.server}<")
                self.err_queue.insert(ErrCode.NAVRTK010_WRONG_SERVER.name)
                self.__flag.clear()
                self.__flag.wait()
                os._exit(0)


    def pause(self):
        '''
        Pauses thread until the resume func will be called
        '''
        self.__flag.clear()

    def resume(self):
        '''
        Resumes thread running
        '''
        self.__flag.set()

class WatchDog(Thread):
    '''
    Watches after "dgpsAge" field at the TPV messages
    coming from gpsd
    '''
    def __init__(self, err_queue: OrderedSetPriorityQueue, log_log:LogLog):
        Thread.__init__(self, name="gpsd_poller")
        self.err_queue = err_queue
        self.log_log = log_log
        while True:
            try:
                #starting the stream of info
                self.gpsd = gps(mode=WATCH_ENABLE)
                break
            except ConnectionRefusedError:
                self.log_log.error("Watchdog: no gpsd running")
            sleep(1)
        self.__flag = Event()
        self.__flag.set()
        self._counter = 0
    def run(self):
        self._counter = time()
        while not killer.kill_now:
            #print('self._counter = ', time()-self._counter)
            try:
                #this will continue to loop and grab EACH set of gpsd info to clear the buffer
                report = self.gpsd.next()
            except (StopIteration,ConnectionResetError):
                #try to connect to gpsd after service being restarted by another thread
                while True:
                    try:
                        #starting the stream of info
                        self.gpsd = gps(mode=WATCH_ENABLE)
                        self._counter = time()
                        break
                    except ConnectionRefusedError:
                        self.log_log.error("Watchdog: no gpsd running")
                    sleep(1)
            try:
                if report['class'] == 'TPV':
                    #print(report)
                    try:
                        if report['status']:
                            #self.log_log.error("Corrections are older than 55 sec")
                            #self.err_queue.insert(ErrCode.NAVRTK004_TIMEOUT.name)
                            #self.__flag.clear()
                            #self.__flag.wait()
                            #os._exit(1)
                            self._counter = time()
                    except KeyError:
                        pass
            except KeyError:
                pass
            if time()-self._counter > 9:
                self.log_log.error("No DGPSAGE message")
                self.err_queue.insert(ErrCode.NAVRTK005_NO_DGPSAGE.name)
                self.__flag.clear()
                self.__flag.wait()
                os._exit(1)
        logger.info("finished running ntripclient...")
        os._exit(0)

    def pause(self):
        '''
        Pauses thread until the resume func will be called
        '''
        self.__flag.clear()

    def resume(self):
        '''
        Resumes thread running
        '''
        self.__flag.set()




if __name__=='__main__':
    try:
        #be caerful with changing an order of the undelying lines
        killer = GracefulKiller()
        logger = LogLog()
        logger.info("Ntrip.service started")

        err_que = OrderedSetPriorityQueue(maxlen = len(ErrCode))

        err_report = ErrReportClass(err_que, logger, redis_host=REDIS_HOST)
        err_report.start()
        while not err_report.is_alive():
            sleep(1)

        parser = argparse.ArgumentParser(description='Runs ntripclient')
        parser.add_argument('server',
                            help='ntripcaster server address')
        parser.add_argument('port',
                            help='ntripcaster server port')
        parser.add_argument('username',
                            help='ntripcaster username (optional)')
        parser.add_argument('password',
                            help='ntripcaster password (optional)')
        parser.add_argument('stream',
                            help='ntripcaster base station (optional)')
        args = parser.parse_args()

        start_ntrip = StartNtrip(err_que, logger, **vars(args))

        CONFIG_BAUDRATE = 'ubxtool -z CFG-UART1-BAUDRATE,115200\
        127.0.0.1:2947:/dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00'
        config_zedf9p(CONFIG_BAUDRATE, logger)

        logger.info("running ntripclient...")
        start_ntrip.start()
        watch_dog = WatchDog(err_que, logger)
        watch_dog.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("finished running ntripclient...")
        os._exit(0)
