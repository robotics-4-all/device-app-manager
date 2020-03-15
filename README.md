# device-app-manager
Component for remotely deploying Applications on Things

## Usage

### Application Manager Daemon
```bash
[I] ➜ ./app_manager.py --help
usage: app_manager.py [-h] [--host HOST] [--port PORT] [--vhost VHOST] [--username USERNAME] [--password PASSWORD] [--queue-size QUEUE_SIZE] [--debug [DEBUG]]

Application Manager CLI.

optional arguments:
  -h, --help            show this help message and exit
  --host HOST           AMQP broker host (IP/Hostname)
  --port PORT           AMQP broker listening port
  --vhost VHOST         Virtual host to connect to.
  --username USERNAME   Authentication username
  --password PASSWORD   Authentication password
  --queue-size QUEUE_SIZE
                        Maximum queue size.
  --debug [DEBUG]       Enable debugging

```

Username defines the unique id of the device (`{thing_id}`).

### Start Application Example

An example demonstrating application deployment call can be found in
`examlles/` examples folder.

Usage example:

```bash
./start_app.py \
    --device-id device2 \
    --host 155.207.33.189 \
    --port 5782 \
    --vhost / \
    --debug \
    --fpath py3_app.tar.gz \
    --app-type py3
```

### Stop Application Example

An example demonstrating application kill call can be found in
`examlles/` examples folder.

Usage example:

```bash
/stop_app.py \
    --app-id f6d5fdf5 \
    --device-id device2 \
    --host 155.207.33.189 \
    --port 5782 \
    --vhost / \
    --debug
```

## Application Manager Endpoints

### RPC Endpoints

All RPC Endpoints are binded to the `DEFAULT` exchange by default.

- Deploy Application:
  - URI: `thing.{thing_id}.appmanager.deploy`
  - DataModel:
    - In: `{"app_type": <py3/tek_ros2_py>, "app_tarball": <BASE64_ENCODED_TARBALL>}`
    - Out: `{"status": <200/404>, "app_id": <unique_app_id>}`
- Kill Application:
  - URI: `thing.{thing_id}.appmanager.kill`
  - DataModel:
    - In: `{"app_id": <unique_app_id>}`
    - Out: `{"status": <200/404>}`
- Is Alive:
  - URI: `thing.{thing_id}.appmanager.is_alive`
  - DataModel:
    - In: `{}`
    - Out: `{}`

### Publish Endpoints

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

- Logs: Sends application logs captured from stdout and stderr to a topic.
  - URI: `thing.{thing_id}.app.{app_id}.logs`
  - DataModel: `{"timestamp": <timestamp_ms>, "log_msg": "<LOG_MSG>"}`

- AppStarted Event: Fires once, on application launch.
  - URI: `thing.{thing_id}.app.{app_id}.started`
  - DataModel: `{}`
