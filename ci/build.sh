#!/usr/bin/env sh
#исполняем в хостовой системе
#########################################################################
SCRIPT_DIR=`dirname $(readlink -f $0)`
REPO_DIR=`realpath ${SCRIPT_DIR}/..`
#########################################################################
IMAGE_ARM=gitlab.cognitivepilot.com:4567/docker/images/armhf/dev:20-v1.2
docker pull ${IMAGE_ARM}
#########################################################################
docker run --rm --workdir=/external-dir --mount source=${REPO_DIR}/ci,target=/external-dir,type=bind \
${IMAGE_ARM} /external-dir/buildGpsd.sh
#########################################################################
docker run --rm --workdir=/external-dir --mount source=${REPO_DIR}/ci,target=/external-dir,type=bind \
${IMAGE_ARM} /external-dir/buildNtripclient.sh