FROM {{ image }}

ENV ROS2_WS /opt/ros_ws
RUN mkdir -p $ROS_WS/src
WORKDIR $ROS_WS
COPY {{ package_src }} ./src

# install ros package dependencies
RUN apt-get update && \
    rosdep update && \
    rosdep install -y \
      --from-paths \
        src \
      --ignore-src && \
    rm -rf /var/lib/apt/lists/*

# build ros package source
RUN . /opt/ros/$ROS_DISTRO/setup.sh && \
    colcon build \
      --cmake-args \
      -DCMAKE_BUILD_TYPE=Release

# copy ros package install via multi-stage
FROM {{ image }}
ENV ROS2_WS /opt/ros_ws
COPY --from=0  $ROS2_WS/install $ROS2_WS/install

# source ros package from entrypoint
RUN sed --in-place --expression \
      '$isource "$ROS2_WS/install/setup.bash"' \
      /ros_entrypoint.sh

CMD ["ros2", "launch", "{{ ros2_package_name }}", "{{ ros2_launcher }}"]
