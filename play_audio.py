# -*- coding: utf-8 -*-
import tomli
import time
from datetime import datetime, timedelta, time as dt_time
import vlc
import os
import logging
import hashlib
import subprocess
import re
import resource
from typing import Union

# Define working directories and file paths
WORKING_DIR = os.path.expanduser("~/Radio")
CONFIG_PATH = os.path.join(WORKING_DIR, "config.toml")
LOG_DIR = os.path.join(WORKING_DIR, "logs")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Initialize log file path with current date
LOG_FILE = os.path.join(LOG_DIR, datetime.now().strftime("%m%d%Y") + ".log")
RESTART_INTERVAL = 24 * 60 * 60  # 24 hours in seconds

# Configure logging root logger and common formatter
logger = logging.getLogger()
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')

def setup_logging():
    global LOG_FILE

    current_log_filename = os.path.join(LOG_DIR, datetime.now().strftime("%m%d%Y") + ".log")

    # Remove any existing FileHandlers from the root logger
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            print(f"Attempting to close and remove old log handler for: {handler.baseFilename}")
            handler.close()
            logger.removeHandler(handler)
            print(f"Successfully closed and removed old log handler for: {handler.baseFilename}")

    # Add the new FileHandler for the current day
    file_handler = logging.FileHandler(current_log_filename)
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)

    LOG_FILE = current_log_filename
    logging.info(f"Logging setup/reconfigured. Now logging to: {LOG_FILE}")

# Initial call to set up logging when the script starts
setup_logging()

def log_memory_usage(enabled=False):
    if not enabled:
        return
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        logging.info(f"Memory Usage (RSS): {usage} KB")
    except Exception as e:
        logging.error(f"Failed to log memory usage: {e}")

# Wrapper for VLC Instance and Media Player
class RadioPlayer:
    def __init__(self, audio_device_name):
        self.audio_device_name = audio_device_name
        self.instance = None
        self.player = None
        self.current_volume = 100
        self._init_vlc()

    def _init_vlc(self):
        if self.player:
            self.player.release()
            self.player = None
        if self.instance:
            self.instance.release()
            self.instance = None

        args = ['--aout=alsa']
        if self.audio_device_name:
             args.append(f'--alsa-audio-device={self.audio_device_name}')
        else:
             logging.warning("No audio device provided to RadioPlayer, using default device.")

        try:
            self.instance = vlc.Instance(*args)
            self.player = self.instance.media_player_new()
            logging.info(f"Initialized VLC Instance with device: {self.audio_device_name}")
        except Exception as e:
             logging.error(f"Failed to initialize VLC: {e}")

    def play_file(self, file_path, volume=None):
        if not self.instance or not self.player:
             logging.error("VLC not initialized, cannot play.")
             return

        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            return

        if volume is not None:
             self.current_volume = volume

        media = self.instance.media_new(file_path)
        self.player.set_media(media)
        self.player.audio_set_volume(self.current_volume)
        self.player.play()
        logging.info(f"Started playing {file_path} with volume {self.current_volume}.")

    def stop(self):
        if self.player:
            self.player.stop()
            logging.info("Stopped playback.")

    def set_volume(self, volume):
        self.current_volume = volume
        if self.player:
            self.player.audio_set_volume(volume)

    def get_state(self):
        if self.player:
            return self.player.get_state()
        return vlc.State.NothingSpecial

    def play_announcement(self, file_path):
        if not self.instance:
            return

        if not os.path.exists(file_path):
            logging.error(f"Announcement file not found: {file_path}")
            return

        temp_player = self.instance.media_player_new()
        media = self.instance.media_new(file_path)
        temp_player.set_media(media)
        temp_player.audio_set_volume(100)
        temp_player.play()
        logging.info(f"Playing announcement: {file_path}")

        while temp_player.get_state() != vlc.State.Ended:
            time.sleep(0.5)

        temp_player.stop()
        temp_player.release()
        logging.info("Announcement finished.")

    def update_device(self, new_device_name):
        if new_device_name != self.audio_device_name:
            logging.info(f"Audio device changed from {self.audio_device_name} to {new_device_name}. Reinitializing VLC.")
            self.audio_device_name = new_device_name
            self.stop()
            self._init_vlc()
            return True
        return False

def load_config(file_path):
    try:
        # NECESSARY CHANGE: tomli requires binary read ('rb')
        with open(file_path, 'rb') as f:
            config = tomli.load(f)
        logging.info("Configuration file loaded successfully.")
        return config
    except Exception as e:
        logging.error(f"Error loading configuration file: {e}")
        return None

def get_current_time():
    return datetime.now().replace(microsecond=0).time()

def get_today_schedule(config):
    default_open_time = config['default_open_time']
    default_close_time = config['default_close_time']
    today = datetime.today().strftime('%A').lower()

    schedule = config['weekly_schedule'].get(today, {})
    open_time = schedule.get('open_time', default_open_time)
    close_time = schedule.get('close_time', default_close_time)

    return open_time, close_time

def get_today_announcements(config):
    default_announcements = config.get('default_announcements', {})
    today = datetime.today().strftime('%A').lower()

    announcements = config.get('announcements', {}).get(today, default_announcements)
    if not announcements:
        announcements = default_announcements
    return announcements

def is_time_between(begin_time, end_time, check_time=None):
    check_time = check_time or get_current_time()
    if begin_time < end_time:
        return check_time >= begin_time and check_time <= end_time
    else:
        return check_time >= begin_time or check_time <= end_time

def detect_raspberry_pi_audio_device() -> Union[str, None]:
    logging.info("Attempting to auto-detect Raspberry Pi audio device...")
    try:
        result = subprocess.run(['aplay', '-l'], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            lines = result.stdout.splitlines()
            device_pattern = re.compile(r"card (\d+): .*\[(.*)\].*device (\d+):")

            found_devices = []
            for line in lines:
                match = device_pattern.search(line)
                if match:
                    card_num = match.group(1)
                    description = match.group(2).lower()
                    device_num = match.group(3)

                    is_headphone = "headphones" in description
                    is_analog = "analog" in description or "analogue" in description
                    is_bcm2835 = "bcm2835" in description
                    is_hdmi = "hdmi" in description

                    if is_headphone or is_analog or (is_bcm2835 and not is_hdmi):
                        device_str = f"hw:{card_num},{device_num}"
                        logging.info(f"Found potential device: {device_str} with description: {description}")
                        if is_headphone:
                            found_devices.insert(0, device_str)
                        else:
                            found_devices.append(device_str)

            if found_devices:
                selected_device = found_devices[0]
                logging.info(f"Auto-detected audio device from 'aplay -l': {selected_device}")
                return selected_device

        else:
            logging.warning(f"'aplay -l' failed: {result.returncode}. Stderr: {result.stderr}")

    except Exception as e:
        logging.error(f"Error during 'aplay -l' parsing: {e}")

    print("FALLBACK: attempting common ALSA device names.")
    common_devices = ["hw:0,0", "hw:1,0"]

    for device in common_devices:
        try:
            parts = device.split(':')
            card_device = parts[1].split(',')
            device_path = f"/dev/snd/pcmC{card_device[0]}D{card_device[1]}p"
            if os.path.exists(device_path):
                logging.info(f"Verified existence of fallback device: {device}")
                return device
        except Exception as e:
            logging.error(f"Error checking fallback device {device}: {e}")

    return None

def get_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

def load_audio_files(music_folder_path):
    audio_files = []
    if not os.path.isdir(music_folder_path):
        logging.warning(f"Music folder not found: {music_folder_path}")
        return audio_files
    for file in os.listdir(music_folder_path):
        if file.lower().endswith(('.mp3', '.wav')):
            audio_files.append(os.path.join(music_folder_path, file))
    if not audio_files:
        logging.warning(f"No audio files found in: {music_folder_path}")
    else:
        logging.info(f"Loaded audio files: {audio_files}")
    return audio_files

# NECESSARY CHANGE: Helper to handle both TOML 1.1 time objects and strings
def parse_time_native(t):
    if isinstance(t, (datetime, dt_time)):
        return t if isinstance(t, dt_time) else t.time()
    return datetime.strptime(str(t), "%H:%M").time()

def main():
    config = load_config(CONFIG_PATH)
    if config is None:
        logging.error("Failed to load configuration. Exiting.")
        return

    # Handle audio device setup
    audio_device_from_config = config.get('audio_output_device')
    audio_device = None

    if audio_device_from_config and audio_device_from_config.strip():
        audio_device = audio_device_from_config.strip()
        logging.info(f"Using audio output device from config file: {audio_device}")
    else:
        logging.info("Audio output device not configured. Attempting auto-detection.")
        audio_device = detect_raspberry_pi_audio_device()

    # NECESSARY CHANGE: Using parse_time_native to handle the new TOML 1.1 time format
    open_time_raw, close_time_raw = get_today_schedule(config)
    open_time = parse_time_native(open_time_raw)
    close_time = parse_time_native(close_time_raw)

    time_before_opening = config['time_before_opening']
    time_after_closing = config['time_after_closing']
    config_check_interval = config['config_check_interval']
    announcements = get_today_announcements(config)

    start_time = (datetime.combine(datetime.now(), open_time) - timedelta(minutes=time_before_opening)).time()
    end_time = (datetime.combine(datetime.now(), close_time) + timedelta(minutes=time_after_closing)).time()

    logging.info(f"Initial schedule loaded: start time: {start_time}, end time: {end_time}")
    logging.info(f"Today's announcements: {announcements}")

    enable_memory_logging = config.get('enable_memory_logging', False)
    log_memory_usage(enable_memory_logging)

    last_hash = get_file_hash(CONFIG_PATH)
    last_config_check_minute = -1
    radio_player = RadioPlayer(audio_device)
    last_announcement_time = None
    file_index = 0
    current_day = datetime.now().day

    # Logic to handle music folder from config or default
    music_folder_path_config = config.get('background_music_folder')
    default_music_folder = os.path.join(WORKING_DIR, "bgmusic")

    if music_folder_path_config and os.path.isdir(music_folder_path_config):
        audio_files = load_audio_files(music_folder_path_config)
    elif os.path.isdir(default_music_folder):
        logging.info(f"No valid 'background_music_folder' in config, using default: {default_music_folder}")
        audio_files = load_audio_files(default_music_folder)
    else:
        logging.warning("No music folder found. No background music will play.")
        audio_files = []

    while True:
        now = get_current_time()
        now_str = now.strftime("%H:%M")

        if datetime.now().day != current_day:
            setup_logging()
            current_day = datetime.now().day
            logging.info(f"Day changed. Log file updated to: {LOG_FILE}")

        if now_str in announcements:
            if last_announcement_time != now_str:
                logging.info(f"Playing announcement: {announcements[now_str]} at {now_str}")
                radio_player.set_volume(20)
                radio_player.play_announcement(os.path.join(WORKING_DIR, announcements[now_str]))
                radio_player.set_volume(100)
                last_announcement_time = now_str

        if audio_files:
            if is_time_between(start_time, end_time):
                state = radio_player.get_state()
                if state == vlc.State.Ended:
                    logging.info(f"Finished playing {audio_files[file_index]}.")
                    file_index = (file_index + 1) % len(audio_files)
                    radio_player.play_file(audio_files[file_index])
                    log_memory_usage(enable_memory_logging)
                elif state in [vlc.State.NothingSpecial, vlc.State.Stopped]:
                    logging.info("Within time window, starting playback.")
                    radio_player.play_file(audio_files[file_index])
                    log_memory_usage(enable_memory_logging)
            else:
                if radio_player.get_state() not in [vlc.State.Stopped, vlc.State.NothingSpecial]:
                     radio_player.stop()
                     log_memory_usage(enable_memory_logging)
        else:
            if radio_player.get_state() not in [vlc.State.Stopped, vlc.State.NothingSpecial]:
                 radio_player.stop()
                 log_memory_usage(enable_memory_logging)

        current_minute = datetime.now().minute
        if current_minute % config_check_interval == 0 and current_minute != last_config_check_minute:
            last_config_check_minute = current_minute
            if get_file_hash(CONFIG_PATH) != last_hash:
                logging.info("Configuration change detected. Reloading main logic.")
                return # Exit to restart main from the outer loop

        time.sleep(1)

if __name__ == "__main__":
    logging.info("Starting the script.")
    while True:
        try:
            main()
        except Exception as e:
            logging.error(f"Error: {e}")
            time.sleep(60)
