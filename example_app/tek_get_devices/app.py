# Copyright 2016 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from robot_communication.srv import GetConnectedDevices, KeyValMemLSet

import rclpy
from rclpy.node import Node


class MinimalClientAsync(Node):

    def __init__(self):
        super().__init__('minimal_client_async')
        nodes = self.get_node_names()
        services = self.get_service_names_and_types()
        topics = self.get_topic_names_and_types()
        self.get_logger().info("Nodes: {}".format(nodes))
        self.get_logger().info("Services: {}".format(services))
        self.get_logger().info("Topics: {}".format(topics))
        self.cli = self.create_client(GetConnectedDevices,
                                      '/nodes_detector/get_connected_devices')
        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting again...')
        self.req = GetConnectedDevices.Request()

    def send_request(self):
        #self.req.a = 41
        #self.req.b = 1
        self.future = self.cli.call_async(self.req)


def main(args=None):
    rclpy.init(args=args)

    minimal_client = MinimalClientAsync()
    minimal_client.send_request()

    while rclpy.ok():
        rclpy.spin_once(minimal_client)
        if minimal_client.future.done():
            if minimal_client.future.result() is not None:
                response = minimal_client.future.result()
                print(response.data)
            else:
                minimal_client.get_logger().info(
                    'Service call failed %r' % (
                        minimal_client.future.exception(),))
            break

    minimal_client.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
