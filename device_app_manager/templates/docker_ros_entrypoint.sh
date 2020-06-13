#!/bin/bash
set -e

# setup ros2 environment
source "/opt/ros/$ROS_DISTRO/local_setup.sh"
source "$ROS_WS/install/local_setup.sh"
exec "$@"
