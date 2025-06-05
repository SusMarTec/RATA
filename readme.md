# RATA (Retail Audio Timing Application) 
#RATA: The "It Works" Store Audio Solution – Approved by IT
Look, if you need simple background music and announcements in your shop, and you've got a Raspberry Pi lying around, RATA is basically that script that just... does it. No fancy frills, no complex setups. You tell it what music to play, when to make an announcement, and it just runs in the background.

It's built with the idea that if something works reliably, you stick with it. You set it up, forget about it, and your customers get their tunes and timely messages. It's especially handy for smaller places that don't need expensive, over-engineered sound systems.

As an IT technician myself, I use this exact script across a chain of stores. It perfectly fulfills its purpose as a low-cost solution that simply works, which means management doesn't have a reason to complain. It's the kind of practical tool that solves a problem without creating new ones.

Key things to know:

What it is: A simple Python script for playing background audio and scheduled announcements.
What it's for: Keeping your store's atmosphere consistent with music and making sure important messages get heard, all automated. It's a reliable, budget-friendly option that keeps operations smooth.
Technical stuff: It's designed to run on Python 3.1 or newer.
Development style: This project gets updates when the developer either feels like adding something new, or more importantly, when there's an actual need to make it work with newer systems or fix something. It's not on a strict release schedule, but it gets the job done.
Tested on: We've confirmed it works well on Raspbian Bullseye and Raspbian Bookworm.
In short: it's a solid, practical tool for a specific job, built to just get out of your way and play some audio, proving its value where it counts: in real-world operations.

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

## Finding the Correct Audio Device

To find the correct audio device for your setup, use the following command:
```
aplay -l
```

This will list all the audio playback devices available. Look for the device that corresponds to your headphones or desired audio output. For example, you might see something like this:

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
  Subdevice #1: subdevice #1
  Subdevice #2: subdevice #2
  Subdevice #3: subdevice #3
  Subdevice #4: subdevice #4
  Subdevice #5: subdevice #5
  Subdevice #6: subdevice #6
  Subdevice #7: subdevice #7
```
In this example, you might use hw:2,0 for the headphones.

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

### Troubleshooting / Advanced Configuration

If you experience issues with the script's stability or long-term operation, you might consider setting up scheduled tasks via crontab. These are examples and may need adjustment based on your specific setup (e.g., service name if you run this as a service).

To edit your crontab, run `crontab -e`.

```cron
# Daily reboot at 5:00 AM (helps clear system state)
0 5 * * * sudo shutdown -r now

# Daily restart of the radio service at 7:00 AM (ensure the script is freshly started)
# Replace 'radio.service' with your actual service name if different.
0 7 * * * sudo systemctl restart radio.service
```
**Note:** Regularly rebooting or restarting services can help maintain stability but might also indicate underlying issues that could be investigated further.
