#!/usr/bin/env sh
#исполняем в хостовой системе
#########################################################################
SCRIPT_DIR=`dirname $(readlink -f $0)`
#########################################################################
conan install ${SCRIPT_DIR} -s arch=armv7 -if ${SCRIPT_DIR}/bin_pack

mv ${SCRIPT_DIR}/bin_pack/gpsd ${SCRIPT_DIR}/../redis_gpsd_ubxtool/
mv ${SCRIPT_DIR}/bin_pack/ntripclient ${SCRIPT_DIR}/../redis_gpsd_ubxtool/