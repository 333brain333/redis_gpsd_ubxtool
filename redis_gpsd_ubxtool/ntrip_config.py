# pylint: disable=arguments-differ
# pylint: disable=protected-access
# pylint: disable=too-many-arguments
# pylint: disable=abstract-method
# pylint: disable=redefined-builtin
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-few-public-methods
# pylint: disable=broad-except
'''
Application aimed to pull redis fileds in order to
maintain cgn_escape_ntrip.service and lora service
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
import json
import redis
from setqueue import OrderedSetPriorityQueue
from health_reporter import Error, ErrorType, ErrorSource, HealthReporter
try:
    from Crypto.Cipher import Blowfish
    from base64 import b64decode
except ModuleNotFoundError:
    pass

with open(Path(__file__).parent / Path('redis_connection_settings.json'), 'r') as file:
    REDIS_CONNECTION_SETTINGS = json.load(file)
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
    '''
    Returns true if programm main process was interrupted
    '''
    kill_now = False
    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, *args):
        '''
        Raise flag to exit gracefully
        '''
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

    def debug(self, text:str)->None:
        '''
        Info level loging into a file and the syslog
        '''
        print(text)
        self.app_log.debug(text)
        syslog.syslog(syslog.LOG_DEBUG, text)

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
    **kwargs) -> None:
        Thread.__init__(self, daemon=True, name="ErrReport")
        self.log_log = log_log
        self._redis_host = kwargs['host']
        self._redis_port = kwargs['port']
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
                self.log_log.debug('ready')
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
                    self.log_log.debug('spin')
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
    **kwargs):
        Thread.__init__(self, name = 'RedisHandler')
        self.redis_host = kwargs['host']
        self.redis_port = kwargs['port']
        self.redis_pssw = kwargs['password']
        self.redis_db = kwargs['db']
        self.strict_redis = redis.StrictRedis(host=self.redis_host,
                                    port=self.redis_port,
                                    password=self.redis_pssw,
                                    db=self.redis_db,
                                    decode_responses=True)
        self.switch_channel = "rtk_switch"
        self.err_que = err_queue
        self.pubsub = self.strict_redis.pubsub()
        self.pubsub.subscribe(self.switch_channel)

    def reconnect(self):
        '''
        Create Redis connection again
        '''
        self.strict_redis = redis.StrictRedis(host=self.redis_host,
                                    port=self.redis_port,
                                    username=None,
                                    password=self.redis_pssw,
                                    db=self.strict_redis,
                                    decode_responses=True)
        self.pubsub = self.strict_redis.pubsub()
        self.pubsub.subscribe(self.switch_channel)

    def is_connected(self)->bool:
        """
        Проверить, активно ли подключение к Redis
        """
        try:
            self.strict_redis.ping()
        except (redis.exceptions.TimeoutError, redis.connection.socket.timeout,
                redis.exceptions.ConnectionError, ConnectionRefusedError):
            return False
        except TypeError:
            return False
        return True

    def run_ntrip(self):
        '''
        Gets password, username, port, stream, server address
        and runs cgn_escape_ntrip.service
        '''
        if self.strict_redis.get('GPS:settings:RTK:passwordEncryption').lower() == 'blowfish':
            try:
                pass_key = self.strict_redis.get('GPS:settings:RTK:password')
                key, enc_pass = ''.join(list(pass_key)[-7:]),\
                        ''.join(list(pass_key)[:-7])
                cipher = Blowfish.new(key)
                decoded_pass = cipher.decrypt(b64decode(enc_pass))
                password =\
                    (decoded_pass[:-int.from_bytes(decoded_pass[-1:], 'big')]).decode('utf-8')
            except Exception as exc:
                logger.error(exc)
                password = ''
        else:
            password = self.strict_redis.get('GPS:settings:RTK:password')
        user = self.strict_redis.get('GPS:settings:RTK:user')
        server = self.strict_redis.get('GPS:settings:RTK:server')
        port = self.strict_redis.get('GPS:settings:RTK:port')
        stream = self.strict_redis.get('GPS:settings:RTK:stream')
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

    def run(self):
        '''
        pub/sub handler
        '''
        while not killer.kill_now:
            if self.is_connected():
                try:
                    message = self.pubsub.get_message()
                except redis.exceptions.ConnectionError:
                    self.pubsub = self.strict_redis.pubsub()
                    self.pubsub.subscribe(self.switch_channel)
                if message:
                    if message['data'] == 'ntrip':
                        logger.info('Ntrip selected')
                        self.run_ntrip()
                    elif message['data'] == 'disabled':
                        logger.info('Off selected')
                        logger.info('stopping cgn_escape_ntrip.service')
                        run('systemctl stop cgn_escape_ntrip.service')
                    elif message['data'] == 'lora':
                        logger.info('LoRa selected')
                        logger.info('stopping cgn_escape_ntrip.service')
                        run('systemctl stop cgn_escape_ntrip.service')
            else:
                logger.error(
                    f"couldn't connect to the redis server {REDIS_CONNECTION_SETTINGS['host']}")
            sleep(1)
        logger.info("finished running ntrip_config...")
        os._exit(0)

if __name__=='__main__':
    try:
        killer = GracefulKiller()
        logger = LogLog()
        logger.info("cgn_ntrip_config.service started")
        err_que = OrderedSetPriorityQueue(maxlen = len(ErrCode))
        err_report = ErrReportClass(err_que, logger, **REDIS_CONNECTION_SETTINGS)
        err_report.start()
        while True:
            try:
                redis_client = RedisHandler(err_que, **REDIS_CONNECTION_SETTINGS)
                break
            except redis.exceptions.ConnectionError:
                logger.error(
                    f"couldn't connect to the redis server {REDIS_CONNECTION_SETTINGS['host']}")
                sleep(1)
        if 'Blowfish' in dir():
            redis_client.strict_redis.set('GPS:settings:RTK:passwordEncryption', 'blowfish')
        else:
            redis_client.strict_redis.set('GPS:settings:RTK:passwordEncryption', 'off')
        if redis_client.strict_redis.get('GPS:settings:RTK:mode') == 'ntrip':
            logger.info('starting cgn_escape_ntrip.service')
            redis_client.run_ntrip()
        sleep(.5)
        redis_client.start()

    except (KeyboardInterrupt, SystemExit):
        redis_client.join()
        logger.info("finished running ntrip_config...")
        os._exit(0)
