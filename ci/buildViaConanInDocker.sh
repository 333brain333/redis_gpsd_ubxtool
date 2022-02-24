#!/usr/bin/env sh
#исполняем в хостовой системе
#########################################################################
SCRIPT_DIR=`dirname $(readlink -f $0)`
REPO_DIR=`realpath ${SCRIPT_DIR}/..`
#########################################################################
IMAGE_x86=gitlab.cognitivepilot.com:4567/docker/images/x86_64/dev:20-latest


docker run --rm --workdir=/external-dir --mount source=${REPO_DIR},target=/external-dir,type=bind \
${IMAGE_x86} /external-dir/ci/buildViaConan.sh