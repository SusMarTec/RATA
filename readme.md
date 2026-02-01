# RATA (Retail Audio Timing Application) 
Look, if you need simple background music and announcements in your shop, and you've got a Raspberry Pi lying around, RATA is basically that script that just... does it. No fancy frills, no complex setups(atleast for the technical people). You tell it what music to play, when to make an announcement, and it just runs in the background.

It's built with the idea that if something works reliably, you stick with it. You set it up, forget about it, and your customers get their tunes and timely messages. It's especially handy for smaller places that don't need expensive, over-engineered sound systems.

As an IT technician myself, I use this exact script across a chain of stores. It perfectly fulfills its purpose as a low-cost solution that simply works, which means management doesn't have a reason to complain. It's the kind of practical tool that solves a problem without creating new ones.

## Technical Stuff
* **Standard:** Config optimized for TOML v1.1.0 
* **Language:** Python 3.1 or newer (Python 3.11+ recommended).
* **Dependencies:** `tomli` and `vlc`.
* **Tested on:** Raspbian Bullseye and Raspbian Bookworm.

## Installation

Make sure your Raspberry Pi is up to date:
```sh
sudo apt update && sudo apt upgrade
```

### 1. Dependencies
This project requires the VLC player and the `tomli` library for TOML v1.1.0 support:
```sh
sudo apt install python3-vlc alsa-utils
pip install tomli
```

### 2. Audio Device
Find your audio device hardware address using:
```sh
aplay -l
```
Look for your desired output (e.g., `hw:1,0`) and use it in the configuration.

## Configuration

RATA now uses the TOML v1.1.0 specification, which allows for much cleaner scheduling. Create a `config.toml` in your working directory (default: `~/Radio/`).

### Native Time Syntax
No more "hacked" strings – use native local time:
```toml
audio_output_device = "hw:1,0"
default_open_time = 09:00   # Native HH:MM format
default_close_time = 21:00

[weekly_schedule]
monday = { open_time = 11:00, close_time = 18:30 }
tuesday = {} # Falls back to defaults
```

### Background Music
* Create a folder named `bgmusic` in your working directory.
* Drop your `.mp3` or `.wav` files there.
* The script will loop everything it finds in that folder.

## Setup the Service (Systemd)

To make it run as a background service that survives reboots:

1. Create the service file:
```sh
sudo nano /etc/systemd/system/radio.service
```

2. Add this content (change `User` if you're not using the default `pi` user):
```ini
[Unit]
Description=RATA Player Service
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/pi/Radio/play_audio.py
WorkingDirectory=/home/pi/Radio
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

3. Enable and start:
```sh
sudo systemctl daemon-reload
sudo systemctl enable radio.service
sudo systemctl start radio.service
```

## Logs
To see what's going on in real-time:
```sh
sudo journalctl -u radio.service -f
```
Working logs are also saved daily in the `logs/` folder inside your working directory.
