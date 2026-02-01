# -*- coding: utf-8 -*-
import tomli
import time
from datetime import datetime, timedelta
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
RESTART_INTERVAL = 24 * 60 * 60  # Script logic for potential 24h restarts

# Configure root logger and format
logger = logging.getLogger()
logger.setLevel(logging.INFO)
log_formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')

def setup_logging():
    """
    Configures and rotates file logging.
    Removes old file handlers and adds a new one for the current day.
    """
    global LOG_FILE
    current_log_filename = os.path.join(LOG_DIR, datetime.now().strftime("%m%d%Y") + ".log")

    # Clear existing file handlers to prevent duplicate logging or file locks
    for handler in logger.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handler.close()
            logger.removeHandler(handler)

    # Attach new file handler for the new day
    file_handler = logging.FileHandler(current_log_filename)
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)
    LOG_FILE = current_log_filename
    logging.info(f"Logging reconfigured. Active log: {LOG_FILE}")

# Initial logging setup
setup_logging()

def log_memory_usage(enabled=False):
    """Logs system memory usage (RSS) if enabled in config."""
    if not enabled:
        return
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        logging.info(f"Memory Usage (RSS): {usage} KB")
    except Exception as e:
        logging.error(f"Failed to log memory usage: {e}")

class RadioPlayer:
    """Wrapper for VLC media player to handle background music and announcements."""
    def __init__(self, audio_device_name):
        self.audio_device_name = audio_device_name
        self.instance = None
        self.player = None
        self.current_volume = 100
        self._init_vlc()

    def _init_vlc(self):
        """Initializes the VLC instance with specific ALSA audio output."""
        if self.player:
            self.player.release()
        if self.instance:
            self.instance.release()

        args = ['--aout=alsa']
        if self.audio_device_name:
             args.append(f'--alsa-audio-device={self.audio_device_name}')
        else:
             logging.warning("Using default audio device.")

        try:
            self.instance = vlc.Instance(*args)
            self.player = self.instance.media_player_new()
            logging.info(f"VLC initialized with device: {self.audio_device_name}")
        except Exception as e:
             logging.error(f"VLC init failed: {e}")

    def play_file(self, file_path, volume=None):
        """Plays a specific audio file."""
        if not self.instance or not self.player:
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
        logging.info(f"Playing: {file_path} (Vol: {self.current_volume})")

    def stop(self):
        if self.player:
            self.player.stop()

    def set_volume(self, volume):
        self.current_volume = volume
        if self.player:
            self.player.audio_set_volume(volume)

    def get_state(self):
        return self.player.get_state() if self.player else vlc.State.NothingSpecial

    def play_announcement(self, file_path):
        """Plays an announcement over the background music by using a temporary player."""
        if not self.instance or not os.path.exists(file_path):
            return
        temp_player = self.instance.media_player_new()
        media = self.instance.media_new(file_path)
        temp_player.set_media(media)
        temp_player.audio_set_volume(100)
        temp_player.play()

        while temp_player.get_state() != vlc.State.Ended:
            time.sleep(0.5)
        temp_player.stop()
        temp_player.release()

    def update_device(self, new_device_name):
        """Reinitializes VLC if the audio output device has changed in config."""
        if new_device_name != self.audio_device_name:
            self.audio_device_name = new_device_name
            self.stop()
            self._init_vlc()
            return True
        return False

def load_config(file_path):
    """Loads TOML configuration. Uses binary mode as required by tomli/TOML v1.1.0."""
    try:
        with open(file_path, 'rb') as f:
            config = tomli.load(f)
        logging.info("Configuration loaded.")
        return config
    except Exception as e:
        logging.error(f"Config load error: {e}")
        return None

def get_current_time():
    return datetime.now().replace(microsecond=0).time()

def get_today_schedule(config):
    """Retrieves today's open and close times from the weekly schedule or defaults."""
    default_open = config['default_open_time']
    default_close = config['default_close_time']
    today = datetime.today().strftime('%A').lower()
    schedule = config['weekly_schedule'].get(today, {})
    return schedule.get('open_time', default_open), schedule.get('close_time', default_close)

def get_today_announcements(config):
    """Retrieves today's announcement list."""
    default = config.get('default_announcements', {})
    today = datetime.today().strftime('%A').lower()
    return config.get('announcements', {}).get(today, default)

def is_time_between(begin_time, end_time, check_time=None):
    """Check if check_time is within the range [begin, end]. Handles midnight wrap."""
    check_time = check_time or get_current_time()
    if begin_time < end_time:
        return check_time >= begin_time and check_time <= end_time
    return check_time >= begin_time or check_time <= end_time

def detect_raspberry_pi_audio_device() -> Union[str, None]:
    """Attempts to auto-detect the RPi audio jack using 'aplay -l'."""
    try:
        result = subprocess.run(['aplay', '-l'], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            device_pattern = re.compile(r"card (\d+): .*\[(.*)\].*device (\d+):")
            for line in result.stdout.splitlines():
                match = device_pattern.search(line)
                if match:
                    card, desc, dev = match.groups()
                    if "headphone" in desc.lower() or "analog" in desc.lower() or "bcm2835" in desc.lower():
                        return f"hw:{card},{dev}"
    except Exception as e:
        logging.error(f"Auto-detection error: {e}")
    return None

def get_file_hash(file_path):
    """Calculates MD5 hash of the config file to detect changes."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

def load_audio_files(music_folder_path):
    """Scans the music folder for mp3 and wav files."""
    audio_files = []
    if not os.path.isdir(music_folder_path):
        return audio_files
    for file in os.listdir(music_folder_path):
        if file.lower().endswith(('.mp3', '.wav')):
            audio_files.append(os.path.join(music_folder_path, file))
    return audio_files

def parse_time(time_val):
    """
    Parses time value.
    TOML 1.1 parsers return datetime.time objects for HH:MM.
    Legacy TOML 1.0 strings are parsed using strptime.
    """
    if isinstance(time_val, (datetime, time)):
        # If it's already a time object (TOML 1.1 native type)
        return time_val if isinstance(time_val, time) else time_val.time()
    # Fallback for strings "HH:MM"
    return datetime.strptime(str(time_val), "%H:%M").time()

def main():
    config = load_config(CONFIG_PATH)
    if not config: return

    # Audio Device Setup
    audio_device_cfg = config.get('audio_output_device')
    audio_device = audio_device_cfg.strip() if audio_device_cfg else detect_raspberry_pi_audio_device()

    # Timing and Schedule Setup
    # Note: parse_time handles both native TOML 1.1 time objects and legacy strings
    open_t = parse_time(get_today_schedule(config)[0])
    close_t = parse_time(get_today_schedule(config)[1])

    buf_before = config['time_before_opening']
    buf_after = config['time_after_closing']
    check_interval = config['config_check_interval']
    announcements = get_today_announcements(config)

    # Calculate actual media playback window
    start_time = (datetime.combine(datetime.now(), open_t) - timedelta(minutes=buf_before)).time()
    end_time = (datetime.combine(datetime.now(), close_t) + timedelta(minutes=buf_after)).time()

    enable_mem_log = config.get('enable_memory_logging', False)
    last_hash = get_file_hash(CONFIG_PATH)
    last_config_check_minute = -1
    radio_player = RadioPlayer(audio_device)

    last_ann_time = None
    file_index = 0
    current_day = datetime.now().day

    # Music folder selection
    music_cfg = config.get('background_music_folder')
    music_dir = music_cfg if (music_cfg and os.path.isdir(music_cfg)) else os.path.join(WORKING_DIR, "bgmusic")
    audio_files = load_audio_files(music_dir)

    while True:
        now = get_current_time()
        now_str = now.strftime("%H:%M")

        # Daily Log Rotation
        if datetime.now().day != current_day:
            setup_logging()
            current_day = datetime.now().day

        # Check for scheduled announcements
        if now_str in announcements:
            if last_ann_time != now_str:
                radio_player.set_volume(20) # Duck music
                radio_player.play_announcement(os.path.join(WORKING_DIR, announcements[now_str]))
                radio_player.set_volume(100) # Restore music
                last_ann_time = now_str

        # Background Music Control
        if audio_files and is_time_between(start_time, end_time):
            state = radio_player.get_state()
            if state in [vlc.State.Ended, vlc.State.NothingSpecial, vlc.State.Stopped]:
                radio_player.play_file(audio_files[file_index])
                file_index = (file_index + 1) % len(audio_files)
                log_memory_usage(enable_mem_log)
        else:
            if radio_player.get_state() not in [vlc.State.Stopped, vlc.State.NothingSpecial]:
                radio_player.stop()

        # Config File Hot-Reload Logic
        cur_min = datetime.now().minute
        if cur_min % check_interval == 0 and cur_min != last_config_check_minute:
            last_config_check_minute = cur_min
            if get_file_hash(CONFIG_PATH) != last_hash:
                logging.info("Config change detected. Reloading...")
                # In a real scenario, we would restart main() or update variables here.
                # Simplified for this specific implementation:
                return # Exit main to let the outer loop restart it

        time.sleep(1)

if __name__ == "__main__":
    logging.info("Starting RATA Service.")
    while True:
        try:
            main()
        except Exception as e:
            logging.error(f"Runtime Error: {e}")
            time.sleep(60)
