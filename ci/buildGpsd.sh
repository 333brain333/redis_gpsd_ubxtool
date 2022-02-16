#!/usr/bin/env sh

#исполняется внутри dev образа или на системе

GPSD_VERSION=gpsd-3.23.1
################################################################################
USER_ID=0
if [ $# -ge 1 ]; then
  USER_ID="$1"
fi

GROUP_ID=0
if [ $# -eq 2 ]; then
  GROUP_ID="$2"
fi

BUILD_DIR=`dirname $(readlink -f $0)`
if [ "$USER_ID" != "0" ] || [ "$GROUP_ID" != "0" ]; then
  BUILD_DIR=/tmp
  cd ${BUILD_DIR}
fi
################################################################################
wget http://download-mirror.savannah.gnu.org/releases/gpsd/${GPSD_VERSION}.tar.gz
tar -xf ${GPSD_VERSION}.tar.gz

cd ${GPSD_VERSION}

python3 /usr/bin/scons -j8 build target_python=python3 shared=1

export DESTDIR=${BUILD_DIR}/gpsd_bin_pack
python3 /usr/bin/scons install
################################################################################
if [ "$USER_ID" != "0" ] || [ "$GROUP_ID" != "0" ]; then
    # change permissions
    chown -R ${USER_ID}:${GROUP_ID} ${BUILD_DIR}
    cp -rp ${BUILD_DIR}/*  `dirname $(readlink -f $0)`
fi
