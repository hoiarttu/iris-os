#!/bin/bash
# 1. Play the video inside the black graphical screen
if [ -f "/home/iris/mirage_gui/assets/media/boot_video.mov" ]; then
    /usr/bin/cvlc --fullscreen --no-video-title-show --no-audio --play-and-exit /home/iris/mirage_gui/assets/media/boot_video.mov > /dev/null 2>&1
fi

# 2. Handoff to the Mirage GUI
cd /home/iris/mirage_gui
exec /usr/bin/python3 main.py
