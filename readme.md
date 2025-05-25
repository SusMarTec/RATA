# RATA (Retail Audio Timing Application) 

This project is designed to play background audio and announcements in a store using a Raspberry Pi with Raspbian. The script plays audio files in a loop and can play announcements at specified times. The configuration is managed via a `config.toml` file.

## Prerequisites

Make sure your Raspberry Pi is up to date:

```sh
sudo apt update
sudo apt upgrade
```
## Dependencies
This project requires the following dependencies to be installed:

Python packages:
   - `toml`
   - `vlc`

I have have not tested on env so i install these system wide.

env testing is "to-do"
```sh
sudo apt install python3-toml python3-vlc
```
Add `python3` into mix if you are not sure if it is latest version for your dist.
But it should be updated if you already did `sudo apt upgrade`

Also make sure that ALSA utils is installed
```sh
sudo apt-get install vlc alsa-utils
```

## Finding the Correct Audio Device and Configuring It

To find the correct audio device for your setup, use the following command in your Raspberry Pi terminal:
```
aplay -l
```

This command will list all the audio playback hardware devices available. Look for the device that corresponds to your desired audio output (e.g., headphones, speakers). The output will show entries like `card X: ..., device Y: ...`. You need to note these `X` (card number) and `Y` (device number).

For example, you might see output similar to this:
```
**** List of PLAYBACK Hardware Devices ****
card 0: vc4hdmi0 [vc4-hdmi-0], device 0: MAI PCM i2s-hifi-0 [MAI PCM i2s-hifi-0]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 1: vc4hdmi1 [vc4-hdmi-1], device 0: MAI PCM i2s-hifi-0 [MAI PCM i2s-hifi-0]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
card 2: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
  Subdevices: 8/8
  Subdevice #0: subdevice #0
  ...
```
If you want to use the 'Headphones' device from this example, it is `card 2`, `device 0`.

**Setting the device in `config.toml`:**

Once you have identified the card and device numbers, you need to set them in the `config.toml` file. Open the `config.toml` file and find the `audio_device` key. Set its value to the card and device numbers as a string, in the format `"X,Y"`.

For the example above (`card 2`, `device 0`), you would set it in `config.toml` as:
```toml
audio_device = "2,0"
```

**Important:** The `play_audio.py` script will automatically add the `hw:` prefix to this value (e.g., it will use `hw:2,0` internally). Therefore, you should **only** include the numbers and the comma (e.g., `"2,0"`) in the `config.toml` file, not the `hw:` prefix. The default `audio_device = "0,0"` in the example `config.toml` also follows this format.

## Configuration

Make sure you have a config.toml file in the same directory as your script. An example configuration file (config.toml) is provided in the repository.

## Setup the Service

Create a systemd service file to manage the script as a service.

1. Create a service file:
```
sudo nano /etc/systemd/system/radio.service
```
2. Add the following content to the radio.service file:
If you are not using rasbian default pi user you can change user= to desired one.
```
[Unit]
Description=Radio Player Service
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/pi/Radio/play_audio.py
WorkingDirectory=/home/pi/Radio
StandardOutput=journal
StandardError=journal
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```
3. Reload systemd to recognize the new service:
```
sudo systemctl daemon-reload
```
4. Enable and start service
```
sudo systemctl enable radio.service
sudo systemctl start radio.service
```
## Logs
To view the logs for the service, use the following command:
```
sudo journalctl -u radio.service
```
You can also see logs under logs folder where script working logs are.
