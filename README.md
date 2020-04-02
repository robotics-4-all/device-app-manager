# device-app-manager
Component for remotely deploying Applications on Things

## Features

Below is the list of features currently supported by the application manager:

- **Get Applications**: Returns the list of installed applications
- **Get Running Applications**: Returns the list of currently running applications
- **Install Application**: Nothing to explain here, the functionality is obvious.
- **Start Application**: Start a previously installed application
- **Stop Application**: Stop a currently running application
- **Delete Application**: Delete an application. Does not terminate the currently running
application instance. Use the **Stop Application** service in case you need such
functionality.

## Supported Application Deployments

### Python3 Application

This kind of application is not stored locally and it is destroyed after
execution.

Tarball contents:

- `app.py`: python executable
- `requirements.txt`: python package dependencies file

### R4A Python3 Application

Tarball contents:

- `app.py`: python executable
- `requirements.txt`: python package dependencies file
- `init.conf`: Describes the necessary variables (and their types, but not the values) the app needs to correctly operate.
- `app.info`: Gives information of the application
- `exec.conf`: Scheduling parameters and stored here. This file is used by the
  application scheduler.

Example `init.conf`:

```yaml
params:
  - name: <string>
    type: <type>
    value: <>
  - name: <string>
    type: <type>
    value: <>
```

where `<type>` is an enumeration and supports the following values:

- `string`
- `float`
- `int`
- `array`

Example `app.info`:

```yaml
name: <string>
version: <string>
type: <string>
elsa_version: <string>
description: <string>
tags: <array_of_strings>
```

Example `exec.conf`:

```yaml
priority: <int>
execution_timestamp: <timestamp>
retry: <bool>
max_retries: <int>
```


## Usage

### Application Manager Daemon

```bash
[I] ➜ ./app_manager.py --help                                                                                
usage: app_manager.py [-h] [--host HOST] [--port PORT] [--vhost VHOST] [--username USERNAME] [--password PASSWORD] [--queue-size QUEUE_SIZE] [--heartbeat HEARTBEAT] [--config CONFIG] [--debug [DEBUG]]

Application Manager CLI

optional arguments:
  -h, --help            show this help message and exit
  --host HOST           AMQP broker host (IP/Hostname)
  --port PORT           AMQP broker listening port
  --vhost VHOST         Virtual host to connect to
  --username USERNAME   Authentication username
  --password PASSWORD   Authentication password
  --queue-size QUEUE_SIZE
                        Maximum queue size.
  --heartbeat HEARTBEAT
                        Heartbeat interval in seconds
  --config CONFIG       Config file path
  --debug [DEBUG]       Enable debugging


```

**NOTE**: Username defines the unique id of the device (`{thing_id}`).

### Configuration

The Application manager daemon can be fully configured via a configuration file,
located at `~/.config/device_app_manager/config`.

A sample configuration file can be found at this repo under the [examples](https://github.com/robotics-4-all/device-app-manager/edit/devel/README.md) directory.

```ini
[core]
debug = 0
deployment_basedir = /tmp/r4a-apps

[platform_control_interfaces]
app_install_rpc_name = thing.x.appmanager.install_app
app_delete_rpc_name = thing.x.appmanager.delete_app
app_list_rpc_name = thing.x.appmanager.apps
get_running_apps_rpc_name = thing.x.appmanager.apps.running
app_start_rpc_name = thing.x.appmanager.start_app
app_stop_rpc_name = thing.x.appmanager.stop_app
is_alive_rpc_name = thing.x.appmanager.is_alive

[platform_monitoring_interfaces]
heartbeat_interval = 10
heartbeat_topic = thing.x.appmanager.heartbeat
connected_event_name = thing.x.appmanager.connected
disconnected_event_name = thing.x.appmanager.disconnected

[platform]
host = r4a-platform.ddns.net
port = 5672
vhost = /
rpc_exchange = DEFAULT
topic_exchange = amq.topic
username = device3
password = device3

[redis]
host = localhost
port = 6379
database = 0
password =
app_list_name = appmanager.apps
```

### Examples
Examples are provided in the **examples** directory of this repository.

We provide an example for each, provided by the application manager, interface.

## Application Manager Platform Control Interfaces

### RPC Endpoints

All RPC Endpoints are binded to the `DEFAULT` exchange by default. Furthermore, json is used as the serialization middleware, which means that input and output messages are json formatted.

#### Get Running Applications Service

Returns the list of currently running applications.

**URI**: `thing.{thing_id}.appmanager.apps.running`

**DataModel**:
  - Input:
  
```
{
}
```
  - Output:

```
{
  "status": <200/404>,
  "apps": [<app>],
  "error": "<error_message>"
}
```

where `app` has the following schema:

```
{
  "name": "test",
  "state": 0,
  "type": "py3",
  "tarball_path": "/home/klpanagi/.apps/app-bf881071.tar.gz",
  "docker_image": "test",
  "docker_container": {"name": "", "id": ""},
  "create_at": 1585761177,
  "updated_at": 1585761226
}
```


#### Get Applications Service

Returns the list of installed applications.

**URI**: `thing.{thing_id}.appmanager.apps`

**DataModel**:
  - Input:
  
```
{
}
```
  - Output:

```
{
  "status": <200/404>,
  "apps": [<app>],
  "error": "<error_message>"
}
```

where `app` has the following schema:

```
{
  "name": "test",
  "state": 0,
  "type": "py3",
  "docker_image": "test",
  "docker_container": {"name": "", "id": ""},
  "create_at": 1585761177,
  "updated_at": 1585761226
}
```

#### Install Application Service

A service call will install and install the input app.

**URI**: `thing.{thing_id}.appmanager.install_app`

**DataModel**:
  - Input:
```
{
  "app_id": "<application_unique_id>",
  "app_type": <py3/r4a_ros2_py>,
  "app_tarball": <BASE64_ENCODED_TARBALL>
}
```
  - Output: 

```
{
  "status": <200/404>,
  "app_id": <application_unique_id>,
  "error": "<error_message>"
}
```

#### Start Application Service

Starts  a pre-installed application.

**URI**: `thing.{thing_id}.appmanager.start_app`

**DataModel**:
  - Input:
  
```
{
  "app_id": <application_unique_id>
}
```
  - Output:
  
```
{
  "status": <200/404>,
  "app_id": <application_unique_id>,
  "error": "<error_message>"
}
```

#### Stop Application Service

Stops a running application.

**URI**: `thing.{thing_id}.appmanager.stop_app`

**DataModel**:
  - Input:
```
{
  "app_id": <application_unique_id>
}
```
  - Output:
```
{
  "status": <200/404>,
  "error": "<error_message>"
}
```

#### Delete Application Service

Delete a pre-installed application.

**URI**: `thing.{thing_id}.appmanager.delete_app`

**DataModel**:
  - Input:      
```
{
  "app_id": <application_unique_id>
}
```
  - Output:
```
{
  "status": <200/404>,
  "error": "<error_message>"
}
```


#### Is Alive Service

Only exists in case someone wants to call this service to see if the
application manager is running.

Not really useful and not recommended. We recommend different
ways for checking the state of the application manager, such as listening to the
**heartbeat topic** -- `thimg.app_manager.heartbeat`. Using the AMQP protocol clients can
also check the state by validating existence of the various service queues.

**URI**: `thing.{thing_id}.appmanager.is_alive`

**DataModel**:
  - Input: `{}`
  - Output: `{}`

### Platform Monitoring Interfaces

These outbound platform monitoring interfaces pushes information from the Edge to the Cloud.
These are Publishers pushing data to an AMQP message broker.

All Publish Endpoints are binded to the `amq.topic` exchange by default.

- Heartbeat Frames: Sends heartbeat frames periodically
  - URI: `thing.{thing_id}.appmanager.heartbeat`
  - DataModel: `{}`

- Connected Event: Fires once when connected to the message broker
  - URI: `thing.{thing_id}.appmanager.connected`
  - DataModel: `{}`

- Disconnected Event: Fires once when disconnected from the message broker
  - URI: `thing.{thing_id}.appmanager.disconnected`
  - DataModel: `{}`


## Per Application Endpoints

Each application deployment creates a series of endpoints.

### Publish Endpoints

#### Log Publisher

Sends application logs captured from stdout and stderr to a topic.

**URI**: `thing.{thing_id}.app.{app_id}.logs`
**DataModel**:
```
{
  "timestamp": <timestamp_ms>,
  "log_msg": "<LOG_MSG>"
}
```

#### Stats Publisher

Sends runtime stats.

**URI**: `thing.{thing_id}.app.{app_id}.stats`
**DataModel**:
```
{
  ...
}
```

#### Application Started Event

Fires once, on application launch.

**URI**: `thing.{thing_id}.app.{app_id}.started`
**DataModel**: `{}`


#### Application Stopped Event

Fires once, on application termination.

**URI**: `thing.{thing_id}.app.{app_id}.stopped`
**DataModel**: `{}`
