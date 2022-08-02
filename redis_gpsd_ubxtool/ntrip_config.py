# pylint: disable=arguments-differ
# pylint: disable=protected-access
# pylint: disable=too-many-arguments
# pylint: disable=abstract-method
# pylint: disable=redefined-builtin
# pylint: disable=too-many-instance-attributes
'''
Application aimed to pull redis fileds in order to
maintain cgn_escape_ntrip.service and others
'''
import logging
from logging.handlers import RotatingFileHandler
from time import sleep
from threading import Thread
import syslog
import os
import signal
import subprocess
from enum import Enum
from pathlib import Path
import redis
from setqueue import OrderedSetPriorityQueue
from health_reporter import Error, ErrorType, ErrorSource, HealthReporter
try:
    from Crypto.Cipher import Blowfish
    from base64 import b64decode
except ModuleNotFoundError:
    pass

REDIS_HOST = '192.168.10.208'
FILENAME = str(Path(__file__).parent.resolve())

class ErrCode(Enum):
    """
    Коды ошибок
    """
    NAVRTK012_MISSING_FIELDS             = (12, "RTK: full all fields")

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
        log_file = f'{str(Path(__file__).parent.resolve())}/ntrip_config.log'
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


def run(command:str):
    '''
    Starts subprocess and waits untill it exits. Reads stdout after subpocess completes.
    '''
    #syslog.syslog(syslog.LOG_INFO, 'Subprocess: "' + command + '"')
    try:
        command_line_process = subprocess.Popen(
            command,
            shell = True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        try:
            process_output, process_error =  command_line_process.communicate()
        except UnicodeDecodeError as err:
            logger.error(f'Decode error: {err}')
            raise err
        #syslog.syslog(syslog.LOG_DEBUG, process_output)
    except OSError as exception:
        logger.error(f'run error: {exception}')
        raise exception
    #else:
    #    syslog.syslog(syslog.LOG_INFO, 'Subprocess finished')
    if process_error:
        logger.error(f'run error: {process_error}')
        os._exit(1)
    return process_output


class RedisHandler(Thread):
    """
    Класс для получения и отправки
    данных через redis
    """
    def __init__(self,
    err_queue: OrderedSetPriorityQueue,
    redis_host='192.168.10.208',
    redis_port=6379,
    redis_pssw=None,
    redis_db=4):
        Thread.__init__(self, name = 'RedisHandler')
        self.redis_host=redis_host
        self.redis_port=redis_port
        self.redis_pssw=redis_pssw
        self.redis_db=redis_db
        self.redis_db = redis.StrictRedis(host=self.redis_host,
                                    port=self.redis_port,
                                    username=None,
                                    password=self.redis_pssw,
                                    db=self.redis_db,
                                    decode_responses=True)
        self.switch_channel = "rtk_switch"
        self.err_que = err_queue
        self.pubsub = self.redis_db.pubsub()
        self.pubsub.subscribe(self.switch_channel)

    def reconnect(self):
        '''
        Create Redis connection again
        '''
        self.redis_db = redis.StrictRedis(host=self.redis_host,
                                    port=self.redis_port,
                                    username=None,
                                    password=self.redis_pssw,
                                    db=self.redis_db,
                                    decode_responses=True)
        self.pubsub = self.redis_db.pubsub()
        self.pubsub.subscribe(self.switch_channel)

    def is_connected(self)->bool:
        """
        Проверить, активно ли подключение к Redis
        """
        try:
            self.redis_db.ping()
        except (redis.exceptions.TimeoutError, redis.connection.socket.timeout,
                redis.exceptions.ConnectionError, ConnectionRefusedError):
            return False
        except TypeError:
            return False
        return True

    def run(self):
        '''
        pub/sub handler
        '''
        while not killer.kill_now:
            if self.is_connected():
                message = self.pubsub.get_message()
                if message:
                    if message['data'] == 'ntrip':
                        logger.info('Ntrip selected')
                        if self.redis_db.get('GPS:settings:RTK:passwordEncryption').lower() == 'on':
                            pass_key = self.redis_db.get('GPS:settings:RTK:password')
                            key, enc_pass = ''.join(list(pass_key)[-7:]),\
                                    ''.join(list(pass_key)[:-7])
                            cipher = Blowfish.new(key)
                            decoded_pass = cipher.decrypt(b64decode(enc_pass))
                            password =\
                                (decoded_pass[:-int.from_bytes(decoded_pass[-1:], 'big')]).decode('utf-8')
                            print(password)
                        else:
                            password = self.redis_db.get('GPS:settings:RTK:password')
                        user = self.redis_db.get('GPS:settings:RTK:user')
                        server = self.redis_db.get('GPS:settings:RTK:server')
                        port = self.redis_db.get('GPS:settings:RTK:port')
                        stream = self.redis_db.get('GPS:settings:RTK:stream')
                        with open(f'{FILENAME}/ntrip_env', 'w') as ntrip_env:
                            ntrip_env.write(
                            f'ARGS={server} {port} {user} {password} {stream}'
                                )
                        if password != '' and\
                            user != '' and\
                            server != '' and\
                            port != '' and\
                            stream != '':
                            logger.info('starting cgn_escape_ntrip.service')
                            run('systemctl start cgn_escape_ntrip.service')
                        else:
                            logger.error('no args for the ntripclient')
                            self.err_que.insert(ErrCode.NAVRTK012_MISSING_FIELDS.name)
                    elif message['data'] == 'disabled':
                        logger.info('Off selected')
                        logger.info('stopping cgn_escape_ntrip.service')
                        run('systemctl stop cgn_escape_ntrip.service')
                    elif message['data'] == 'lora':
                        logger.info('LoRa selected')
                        logger.info('stopping cgn_escape_ntrip.service')
                        run('systemctl stop cgn_escape_ntrip.service')
            else:
                logger.error(f"couldn't connect to the redis server {REDIS_HOST}")
                self.reconnect()
            sleep(1)
        logger.info("finished running ntrip_config...")
        os._exit(0)

if __name__=='__main__':
    try:
        killer = GracefulKiller()
        logger = LogLog()
        logger.info("cgn_ntrip_config.service started")
        err_que = OrderedSetPriorityQueue(maxlen = len(ErrCode))
        err_report = ErrReportClass(err_que, logger, redis_host=REDIS_HOST)
        err_report.start()
        redis_client = RedisHandler(err_que, redis_host=REDIS_HOST)
        while True:
            if redis_client.is_connected():
                break
            logger.error(f"couldn't connect to the redis server {REDIS_HOST}")
            sleep(1)
        if 'Blowfish' in dir():
            redis_client.redis_db.set('GPS:settings:RTK:passwordEncryption', 'on')
        else:
            redis_client.redis_db.set('GPS:settings:RTK:passwordEncryption', 'off')
        if redis_client.redis_db.get('GPS:settings:RTK:mode') == 'ntrip':
            logger.info('starting cgn_escape_ntrip.service')
            run('systemctl start cgn_escape_ntrip.service')
        sleep(.5)
        redis_client.start()

    except (KeyboardInterrupt, SystemExit):
        redis_client.join()
        logger.info("finished running ntrip_config...")
        os._exit(0)
