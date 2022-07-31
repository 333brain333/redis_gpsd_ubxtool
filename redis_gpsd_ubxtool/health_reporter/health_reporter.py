from typing import get_type_hints
import json
import redis
import datetime
import enum
import time
import threading


class ErrorType(enum.Enum):
    none             = (0, "none")
    warning          = (1, "warning")
    error            = (2, "error")
    # ошибки которая не будет выведена у клиента, но ляжет в базу, телеметрию
    silent_error     = (3, "silent_error")
    # ворнинг который не будет выведен у клиента, но ляжет в базу, телеметрию
    silent_warning   = (4, "silent_warning")

    def __init__(self, id, text):
        self.text = text
        self.id = id

class ErrorSource(enum.Enum):
    """
    Службы-источники ошибок
    """
    unknown        = (0, "Unknown")
    planner        = (1, "Planner")
    DBW            = (2, "DBW")
    perception     = (3, "Perception")
    localizer      = (4, "Localizer")
    GPSservice     = (5, "GPS-service")
    CANdevices     = (6, "CAN-devices")
    JetsonHardware = (7, "jetson hardware")
    NavRTK         = (8, "RTK navigational")

    def __init__(self, id, text):
        self.text = text
        self.id = id

class Error:
    def __init__(self, source: ErrorSource, type: ErrorType, code: str):
        self.source = source
        self.type = type
        self.code = code


class HealthReporter:
    """
    Класс для передачи сообщений об ошибках
    и keepalive в Redis.
    """
    def __init__(self, err_source : ErrorSource, redis_host=None, redis_port=None, redis_pssw=None, redis_db=1):
        self.db = redis.StrictRedis(host=redis_host, 
                                    port=redis_port,
                                    username=None,
                                    password=redis_pssw, 
                                    db=redis_db, 
                                    decode_responses=True)
        self.keepalives_channel = "keepalives"
        self.errors_channel = "raw_errors"
        self.source = err_source
        self.keepalive_cycle_sec = 20
        self.redis_config_ready_ev = threading.Event()
        self.initConfig()


    def isRedisConfigReady(self):
        """
        Узнать, сконфигурирована ли система в целом.
        Если система не сконфигурирована, 
        сообщать об ошибках не требуется.
        """
        return self.redis_config_ready_ev.is_set()


    def getKeepaliveCycleTimeSec(self):
        """
        Сообщает, не реже какой периодичности 
        необходимо рапортовать о keepalive
        """
        return self.keepalive_cycle_sec

    def getSecondsToNextKeepalive(self):
        """
        Через сколько секунд нужно прислать новый keepalive.
        Вернет отрицательное значение, если с последней отправки 
        прошло больше чем getKeepaliveCycleTimeSec() секунд.
        """
        return self.last_keepalive_cycle_ts + self.keepalive_cycle_sec - time.time()

    def keepalive(self):
        """
        Сообщить keepalive от данного source
        """
        self.db.publish(self.keepalives_channel, self.source.text)
        self.last_keepalive_cycle_ts = time.time()
        return


    def pushError(self, error: Error):
        """
        Сообщить об активной ошибке.
        Необходимо передавать активные ошибки 
        не реже периодичности цикла
        (getKeepaliveCycleTimeSec)
        """
        data_dict = {
        "type" : error.type.text, 
        "device" : error.source.text, 
        "timestamp" : datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds'),
        "text_ru" : "To be replaced from Redis dict",
        "text_en" : "To be replaced from Redis dict",
        "error_code" : error.code
        }
        error_str = json.dumps(data_dict)
        self.db.publish("raw_errors", error_str)


    def initConfig(self):
        if not self.isConnected():
            return False
        keepalive_cycle = self.db.get("health_monitor_cfg:reporter_cycle_sec")
        if keepalive_cycle:
            self.keepalive_cycle_sec = int(keepalive_cycle) 
        self.last_keepalive_cycle_ts = time.time()

        self.__checkRedisConfigReady()

        self.pubsub = self.db.pubsub()
        self.pubsub.subscribe(**{"config_ready": self.__checkRedisConfigReady})
        self.pubsub.run_in_thread(sleep_time=.01, daemon=True)
        return True


    def isConnected(self):
        """
        Проверить, активно ли подключение к Redis
        """
        try:
            self.db.ping()
        except (redis.exceptions.TimeoutError, redis.connection.socket.timeout,
                redis.exceptions.ConnectionError, ConnectionRefusedError) as e:
            return False
        except (TypeError):
            return False
        return True

    
    def __checkRedisConfigReady(self, msg = None):
        if self.db.get("health_monitor_cfg:config_ready") == "true":
            self.redis_config_ready_ev.set()


