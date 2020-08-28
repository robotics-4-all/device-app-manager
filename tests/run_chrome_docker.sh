#!/usr/bin/env bash

docker run -it \
    --rm \
    --net host \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -e DISPLAY=unix$DISPLAY \
    -v $HOME/Downloads:/root/Downloads \
    -v $HOME/.config/google-chrome/:/data \
    --device /dev/snd \
    --name chrome \
    jess/chrome \
    --no-sandbox
