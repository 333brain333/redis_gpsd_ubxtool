#!/usr/bin/env sh

#исполняется внутри dev образа или на системе

NTRIPCLIENT_VERSION=1.51
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
wget --no-check-certificate -O ntripclient-${NTRIPCLIENT_VERSION}.tar.gz https://github.com/nunojpg/ntripclient/archive/refs/tags/v${NTRIPCLIENT_VERSION}.tar.gz
tar -xf ntripclient-${NTRIPCLIENT_VERSION}.tar.gz

cd ntripclient-${NTRIPCLIENT_VERSION}

make
mkdir -p ${BUILD_DIR}/ntripclient_bin_pack/
cp ntripclient ${BUILD_DIR}/ntripclient_bin_pack
################################################################################
if [ "$USER_ID" != "0" ] || [ "$GROUP_ID" != "0" ]; then
    # change permissions
    chown -R ${USER_ID}:${GROUP_ID} ${BUILD_DIR}
    cp -rp ${BUILD_DIR}/*  `dirname $(readlink -f $0)`
fi