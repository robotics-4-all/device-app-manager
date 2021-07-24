# device-app-manager
Component for remotely deploying Applications on Edge Devices.

![app_managerArchitecture](/assets/img/app_manager.png)

- **Redis DB/Cache**: Uses redis to cache data and store application installations and deployments.
- **Docker Container Engine**: Applications are deployed in docker containers. This is achieved by
calling the **docker-ce agent** API to build, run, stop and remove images and containers. It is also
responsible to attach to proper network(s)m or even to the local host network and pid and ipc namespace, when required.

By viewing the above architecture diagram, someone may think of "Why Redis"? The answer is pretty. We wanted to have as minimal memory footprint that is well tested on end embedded devices, such as Raspberry PIs.

**Note**: For R4A ROS2 Applications it is necessary to attach the application container to the host IPC and PID Namespace. Elsewhere, DDS communication using FastRTPS could not resolve services in localhost. DDS automatically switched to shared memory communication mode when discovering endpoints running on localhost. Because of the fact that docker containers are isolated from the host machine (up to some level and fully configured - net/pid/ipc stack) by default this type of communication (shared memory) could not be resolved.

## Features

Below is the list of features currently supported by the application manager:

- **Get Applications**: Returns the list of installed applications
- **Get Running Applications**: Returns the list of currently running applications
- **Install Application**: Nothing to explain here, the functionality is obvious.
- **Start Application**: Start a previously installed application
- **Stop Application**: Stop a currently running application
- **Delete Application**: Delete an application. Does not terminate the currently running application instance. Use the **Stop Application** service in case you need such functionality.
- **FastDeploy Application**: Simple build-and-deploy service that does not store the application in local repository

## Supported Application Types

### Python3 Application

Can be any Python3 Application. Use the `requirements.txt` file to define python package dependencies to be installed.

Tarball contents:

- `app.py`: python executable
- `requirements.txt`: python package dependencies file

**Keyword**: `py3`

### R4A Python3 Application

Tarball contents:

- `app.py`: python executable
- `requirements.txt`: python package dependencies file
- `init.conf`: Describes the necessary variables (and their types, but not the values) the app needs to correctly operate.
- `app.info`: Gives information of the application
- `exec.conf`: Scheduling parameters and stored here. This file is used by the
  application scheduler.

**Keyword**: `r4a_ros2_py`

**Example `init.conf`**:

```yaml
params:
  - name: <string>
    placeholder: <string>
    type: <datatype>
    value: <string>
  - name: <string>
    placeholder: <string>
    type: <datatype>
    value: <string>
```

where `<datatype>` is an enumeration and supports the following values:

- `string`
- `float`
- `int`
- `array`

**Example `app.info`**:

```yaml
name: <string>
version: <string>
type: "r4a_ros2_py"
description: <string>
tags: <array_of_strings>
```

**Example `exec.conf`**:

```yaml
priority: <int>
execution_timestamp: <timestamp>
retry: <bool>
max_retries: <int>
start_on_boot: <bool>
```

### NodeRED Application

Tarball contents:

- `flows.json`: NodeRED application as exported from the IDE in json format
- `package.json`: Includes nodered app (nodered package) information, such as
dependencies. Look [here](https://nodered.org/docs/creating-nodes/packaging) for
more information
- `settings.json`: NodeRED instance settings. Look [here](https://nodered.org/docs/user-guide/runtime/settings-file) for more information.

**Keyword**: `nodered`

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

A sample configuration file can be found at this repo under the [examples](https://github.com/robotics-4-all/device-app-manager/tree/master/examples) directory.

```ini
[core]
debug = 1
app_build_dir = /tmp/app-manager/apps/
stop_apps_on_exit = 1
keep_app_tarballs = 1
app_storage_dir = ~/.apps/
uri_namespace = app_manager
device_id = device0

[control]
app_install_rpc_name = install_app
app_delete_rpc_name = delete_app
app_list_rpc_name = apps
get_running_apps_rpc_name = apps.running
app_start_rpc_name = start_app
app_stop_rpc_name = stop_app
is_alive_rpc_name = is_alive
fast_deploy_rpc_name = fast_deploy

[monitoring]
heartbeat_interval = 10
heartbeat_topic = heartbeat
connected_event_name = connected
disconnected_event_name = disconnected

[applications]
app_started_event = app.{APP_ID}.started
app_stopped_event = app.{APP_ID}.stopped
app_logs_topic = app.{APP_ID}.logs
app_stats_topic = app.{APP_ID}.stats
publish_app_logs  = 1
publish_app_stats = 1
app_ui_storage_dir = ~/.config/device_app_manager

[ui_manager]
start_rpc = ui.custom.start
stop_rpc = ui.custom.stop

[rhasspy]
add_sentences_rpc = rhasspy_ctrl.add_sentences
delete_sentences_rpc = rhasspy_ctrl.delete_sentences

[audio_events]
enable = 1
speak_action_uri = /robot/robot_1/actuator/audio/speaker/usb_speaker/d0/id_0/speak

[platform_broker]
uri_namespace = thing.{DEVICE_ID}
logging = 0
type = AMQP
host = r4a-platform.ddns.net
port = 5782
; Vhost is used only in case of AMQP broker
vhost = /
; DB is used only in case of Redis broker
db = 0
rpc_exchange = DEFAULT
topic_exchange = amq.topic
username = device0
password = device0

[local_broker]
uri_namespace =
logging = 0
type = REDIS
host = localhost
port = 6379
; Vhost is used only in case of AMQP broker
vhost = /
; DB is used only in case of Redis broker
db = 0
; username = device3
; password = device3

[redis]
host = localhost
port = 6379
database = 0
password =
app_list_name = app_manager.apps
```

#### Core Parameters

`Section: [core]`

- **debug**: Enable/Disable debug mode
- **app_build_dir**: Temp app directory. Used to extract and build apps.
- **stop_apps_on_exit**: Stop all applications before exiting  (DEPRECATED)
- **keep_app_tarballs**: Keep Application Tarballs locally (DEPRECATED)
- **app_storage_dir**: Directory to temporary store apps (DEPRECATED)
- **uri_namespace**: Global Namespace to add on all interfaces (for app_manager only)
- **device_id**: The ID of the device. Used to add device information on URIs, by using the {DEVICE_ID} in config

#### Control Interfaces Parameters

`Section: [control]`

- **app_install_rpc_name**:
- **app_delete_rpc_name**:
- **app_list_rpc_name**:
- **get_running_apps_rpc_name**:
- **app_start_rpc_name**:
- **app_stop_rpc_name**:
- **is_alive_rpc_name**:
- **fast_deploy_rpc_name**:

#### Monitoring Interfaces Parameters

`Section: [monitoring]`

- **heartbeat_interval**:
- **heartbeat_topic**: Topic to publish heartbeat messages
- **connected_event_name**: app_manager-Connected Event Name
- **disconnected_event_name**: app_manager-Disconnected Event Name

#### Application Deployment Parameters

`Section: [applications]`

- **app_started_event**:
- **app_stopped_event**:
- **app_logs_topic**:
- **app_stats_topic**:
- **app_ui_storage_dir**: Directory to store App UI components

#### UI-Manager Parameters

`Section: [ui_manager]`

- **start_rpc**:
- **stop_rpc**:

#### Rhasspy Parameters

`Section: [rhasspy]`

- **add_sentences_rpc**:
- **delete_intent_rpc**:

#### Audio-Events Parameters

`Section: [audio_events]`

- **enable**: Enable/Disable Audio-Events for `on_app_started` and `on_app_stopped`
- **speak_action_uri**:

#### Platform Broker Parameters

`Section: [platform_broker]`

- **uri_namespace**: Prefix Namespace to add for all endpoints (Platform Connections)
- **type**: Type of the Platform broker. Currently support `AMQP` and `REDIS`
- **host**: Platform broker host
- **port**: Platform broker port
- **vhost**: Platform broker vhost. Only used if `type=AMQP`
- **db**: Platform broker db. Only used if `type=REDIS`
- **username**:
- **password**:

#### Local Broker Parameters

`Section: [local_broker]`

- **uri_namespace**: Prefix Namespace to add for all endpoints (Platform Connections)
- **type**: Type of the Platform broker. Currently support `AMQP` and `REDIS`
- **host**: Platform broker host
- **port**: Platform broker port
- **vhost**: Platform broker vhost. Only used if `type=AMQP`
- **db**: Platform broker db. Only used if `type=REDIS`
- **username**:
- **password**:


### Examples
Examples are provided in the **examples** directory of this repository.

We provide an example for each, provided by the application manager, interface.


## AppManager Control Interfaces

### RPC Endpoints

All RPC Endpoints are binded to the `DEFAULT` exchange by default. Furthermore, json is used as the serialization middleware, which means that input and output messages are json formatted.

#### Get Running Applications Service

Returns the list of currently running applications.

**Default Local URI**: `app_manager.apps.running`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.apps.running`

**DataModel**:
  
```json
Request
--------
{}

Response
--------
{
  "status": <200/404>,
  "apps": [<app>],
  "error": "<error_message>"
}

```

where `app` has the following schema:

```json
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

**Default Local URI**: `app_manager.apps`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.apps`

**DataModel**:
  
```json
Request
--------
{}

Response
--------
{
  "status": <200/404>,
  "apps": [<app>],
  "error": "<error_message>"
}
```

where `app` has the following schema:

```json
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

Supported Applications are:
- `py3`: Simple Python3 Application
- `r4a_ros2_py`: R4A ROS2 Application

**Default Local URI**: `app_manager.install_app`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.install_app`

**DataModel**:

```json
Request
--------
{
  "app_id": "<application_unique_id>",
  "app_type": <r4a_ros2_py>,
  "app_tarball": <BASE64_ENCODED_TARBALL>
}

Response
--------
{
  "status": <200/404>,
  "app_id": <application_unique_id>,
  "error": "<error_message>"
}
```

#### Start Application Service

Starts  a pre-installed application.

**Default Local URI**: `app_manager.start_app`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.start_app`

**DataModel**:

```json
Request
--------
{
  "app_id": <application_unique_id>,
  "app_args": []
}

Response
--------
{
  "status": <200/404>,
  "app_id": <application_unique_id>,
  "error": "<error_message>"
}
```

`app_args` can be used to pass arguments to the application.
Array of flags/values.

**Example RPC**:

`start_app(app_id="test", app_args=['-l', 'a'])`

#### Stop Application Service

Stops a running application.

**Default Local URI**: `app_manager.stop_app`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.stop_app`

**DataModel**:

```json
Request
--------
{
  "app_id": <application_unique_id>
}

Response
--------
{
  "status": <200/404>,
  "error": "<error_message>"
}
```

**Example RPC**:

`stop_app(app_id="test")`

#### Delete Application Service

Delete a pre-installed application.

**Default Local URI**: `app_manager.delete_app`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.delete_app`

**DataModel**:

```json
Request
--------
{
  "app_id": <application_unique_id>
}

Response
--------
{
  "status": <200/404>,
  "error": "<error_message>"
}
```

**Example RPC**:

`delete_app(app_id="test")`

#### Fast-Deploy Application Service

A service call will run application without storing it in local repository

Supported Applications are:
- `py3`: Simple Python3 Application
- `r4a_commlib`: R4A ROS2 Application

**Default Local URI**: `app_manager.install_app`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.install_app`

**DataModel**:

```json
Request
--------
{
  "app_id": "<application_unique_id>",
  "app_type": "r4a_commlib",
  "app_tarball": <BASE64_ENCODED_TARBALL>
  "app_args": []
}

Response
--------
{
  "status": <200/404>,
  "app_id": <application_unique_id>,
  "error": "<error_message>"
}
```

#### Is Alive Service

Only exists in case someone wants to call this service to see if the
application manager is running.

Not really useful and not recommended. We recommend different
ways for checking the state of the application manager, such as listening to the
**heartbeat topic**. Using the AMQP protocol clients can
also check the state by validating existence of the various service queues.

**Default Local URI**: `app_manager.is_alive`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.is_alive`

**DataModel**:

```json
Request
--------
{}

Response
--------
{}
```

### Monitoring Interfaces

These outbound platform monitoring interfaces pushes information from the Edge to the Cloud.
These are Publishers pushing data to an AMQP message broker.

All Publish Endpoints are binded to the `amq.topic` exchange by default.

- Heartbeat Frames: Sends heartbeat frames periodically
  - **Default Local URI**: `app_manager.heartbeat`
  - **Default Platform URI**: `thing.{DEVICE_ID}.app_manager.heartbeat`
  - DataModel: `{}`

- Connected Event: Fires once when connected to the message broker
  - **Default Local URI**: `app_manager.connected`
  - **Default Platform URI**: `thing.{DEVICE_ID}.app_manager.connected`
  - DataModel: `{}`

- Disconnected Event: Fires once when disconnected from the message broker
  - **Default Local URI**: `app_manager.disconnected`
  - **Default Platform URI**: `thing.{DEVICE_ID}.app_manager.disconnected`
  - **DataModel**: `{}`


## Per Application Endpoints

Each application deployment creates a series of endpoints.

### Publish Endpoints

#### Log Publisher

Sends application logs captured from stdout and stderr to a topic.

**Default Local URI**: `app_manager.app.{app_id}.logs`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.app.{app_id}.logs`

**DataModel**:

```json
{
  "timestamp": <timestamp_ms>,
  "log_msg": "<LOG_MSG>"
}
```

#### Stats Publisher

Sends runtime stats.

**Default Local URI**: `app_manager.app.{app_id}.stats`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.app.{app_id}.stats`

**DataModel**:

```json
{
  ...
}
```

#### Application Started Event

Fires once, on application launch.

**Default Local URI**: `app_manager.app.{app_id}.started`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.app.{app_id}.started`

**DataModel**: `{}`


#### Application Stopped Event

Fires once, on application termination.

**Default Local URI**: `app_manager.app.{app_id}.stopped`

**Default Platform URI**: `thing.{DEVICE_ID}.app_manager.app.{app_id}.stopped`

**DataModel**: `{}`


## Considerations

- Investigate other container engines or builds that are effective for low-processing devices.
  - [BalenaEngine](https://github.com/balena-os/balena-engine)
