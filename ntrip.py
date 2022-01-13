import subprocess
import syslog
import time



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

out = run('ubxtool -P 27.12 -z CFG-UART1-BAUDRATE,115200 127.0.0.1:2947:/dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00')
if 'UBX-ACK-ACK' in out:
    print('Baudrate config OK')
else:
    print('Baudrate config FAIL')
time.sleep(1)
out = run('ubxtool -P 27.12 -z CFG-UART1OUTPROT-NMEA,0 127.0.0.1:2947:/dev/serial/by-id/usb-u-blox_AG_-_www.u-blox.com_u-blox_GNSS_receiver-if00')
if 'UBX-ACK-ACK' in out:
    print('NMEA OUT config OK')
else:
    print('NMEA OUT config FAIL')
time.sleep(1)
out = run('/home/agrodroid/ntripclient/ntripclient -s 82.202.202.138 -r 2102 -u msc1745 -p 934857 -m ROPS -D /dev/ttyS4 -B 115200 -M 1')