# echoscreen
Screen mirroring/extending client for Linux. Compatible with SpaceDesk server 2.2.15 . Developed and tested on Ubutu 24.04

## Purpose
Implement the binary protocol used by the spacedesk solution, in order to use a Linux laptop as a secondary screen for a computer running the Server (also called "Driver") software. I use it with a wired gigabit ethernet connection for productivity tools and photo editing ; there is virtually no latency.

## Installation
 1. Install the system requirements: ```apt install gstreamer1.0-qt6 gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-vaapi```
 2. Clone (or download) the repo: ```git clone https://github.com/GregoireDelannoy/echoscreen.git```
 3. Create a virtual env and set you python to use it: ```python3 -m venv env && source .env/bin/activate```
 4. Install the python dependencies: ```pip install -r ./requirements.txt```

## Usage
As of now, the application has to be launched with the commandline, and then spawns a GUI for displaying the video feed.

Basic usage, replacing the IP address with the one of your server: ```python app.py 192.168.1.42```

Press *F11* or *F* to go fullscreen. *ESC* to escape fullscreen or quit. *Q* to quit directly.

### Options
 * ```-p 12345``` TCP port
 * ```-r 1024x768``` Video resolution
 * ```-q 70``` Video quality
 * ```-d``` Debug flag

## Supported
 * Arbitrary screen resolutions
 * Streaming quality
 * Fullscreen mode

## Not yet supported
**Please let me know if you're interested in any specific feature!**
 * Full GUI with settings remembered
 * Easier distribution for less technical users
 * Automatic server discovery (there seems to be someting in the Android client???)
 * Password support
 * Audio
 * Pass a Qt widget directly to gstreamer, avoid unecessary frame unpacking + remove numpy dependency
 * Mouse and keyboard events