# -*- coding: utf-8 -*-
import toml
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

# Define working directories and file paths / Määrake töökaustad ja failiteed
WORKING_DIR = os.path.expanduser("~/Radio")
CONFIG_PATH = os.path.join(WORKING_DIR, "config.toml")
LOG_DIR = os.path.join(WORKING_DIR, "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
# LOG_FILE global variable: Its role changes. It will be updated by setup_logging.
# Initialize it here for clarity, though setup_logging will define its operational value.
LOG_FILE = os.path.join(LOG_DIR, datetime.now().strftime("%m%d%Y") + ".log")
RESTART_INTERVAL = 24 * 60 * 60  # 24 hours in seconds / 24 tundi sekundites

# Configure logging / Seadistage logimine
# Get the root logger once at the module level / Hangi juurlogija üks kord mooduli tasemel
logger = logging.getLogger()
# Set the root logger level. This is important for messages to be passed to handlers. / Määra juurlogija tase. See on oluline, et sõnumid jõuaksid halduriteni.
logger.setLevel(logging.INFO) 
# Define a common log formatter / Määra ühine logivormindaja
log_formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')

def setup_logging():
    """
    Configures file logging. Removes old file handlers and adds a new one
    for the current day's log file. Ensures logs are written to a new file
    when the date changes.

    Seadistab failipõhise logimise. Eemaldab vanad failihaldurid ja lisab uue
    praeguse päeva logifaili jaoks. Tagab, et logid kirjutatakse uude faili,
    kui kuupäev muutub.
    """
    global LOG_FILE # To update the global LOG_FILE variable's value / Globaalse LOG_FILE muutuja väärtuse uuendamiseks

    current_log_filename = os.path.join(LOG_DIR, datetime.now().strftime("%m%d%Y") + ".log")

    # Remove any existing FileHandlers from the root logger / Eemalda kõik olemasolevad FileHandlerid juurlogijast
    # Iterate over a copy of logger.handlers list to allow modification / Itereeri logger.handlers nimekirja koopia üle, et võimaldada muutmist
    for handler in logger.handlers[:]: 
        if isinstance(handler, logging.FileHandler):
            # Using print for this critical step, as logging might be in transition. / Kasuta printi selle kriitilise sammu jaoks, kuna logimine võib olla ülemineku faasis.
            print(f"Attempting to close and remove old log handler for: {handler.baseFilename}")
            handler.close()
            logger.removeHandler(handler)
            print(f"Successfully closed and removed old log handler for: {handler.baseFilename}")

    # Add the new FileHandler for the current day / Lisa uus FileHandler praeguse päeva jaoks
    file_handler = logging.FileHandler(current_log_filename)
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)
    
    # Update the global LOG_FILE variable to the new path / Uuenda globaalne LOG_FILE muutuja uue failiteega
    LOG_FILE = current_log_filename
    
    # Log confirmation to the new log file. This message is crucial for confirming the switch. / Logi kinnitus uude logifaili. See sõnum on lülituse kinnitamiseks ülioluline.
    logging.info(f"Logging setup/reconfigured. Now logging to: {LOG_FILE}")


# Initial call to set up logging when the script starts. / Esmane logimise seadistamise kutse skripti käivitamisel.
# This replaces the old setup_logging() call at the module level.
setup_logging()

def log_memory_usage(enabled=False):
    if not enabled:
        return
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux returns ru_maxrss in kilobytes.
        logging.info(f"Memory Usage (RSS): {usage} KB")
    except Exception as e:
        logging.error(f"Failed to log memory usage: {e}")

class RadioPlayer:
    def __init__(self, audio_device_name):
        self.audio_device_name = audio_device_name
        self.instance = None
        self.player = None
        self.current_volume = 100
        self._init_vlc()

    def _init_vlc(self):
        # Release existing resources if any
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

        # Create a temporary player from the same instance
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

# Function to load configuration file / Funktsioon konfiguratsioonifaili laadimiseks
def load_config(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config = toml.load(f)
        logging.info("Configuration file loaded successfully.")
        return config
    except Exception as e:
        logging.error(f"Error loading configuration file: {e}")
        return None

# Function to get current time / Funktsioon praeguse aja saamiseks
def get_current_time():
    return datetime.now().replace(microsecond=0).time()

# Function to determine today's schedule / Funktsioon tänase ajakava määramiseks
def get_today_schedule(config):
    default_open_time = config['default_open_time']
    default_close_time = config['default_close_time']
    today = datetime.today().strftime('%A').lower()  # Get today's day name / Saate tänase päeva nime

    schedule = config['weekly_schedule'].get(today, {})
    open_time = schedule.get('open_time', default_open_time)
    close_time = schedule.get('close_time', default_close_time)

    return open_time, close_time

# Function to determine today's announcements / Funktsioon tänaste teadaannete määramiseks
def get_today_announcements(config):
    default_announcements = config.get('default_announcements', {})
    today = datetime.today().strftime('%A').lower()  # Get today's day name / Saate tänase päeva nime

    announcements = config.get('announcements', {}).get(today, default_announcements)
    if not announcements:
        announcements = default_announcements
    return announcements

# Function to check if the current time is between two times / Funktsioon kontrollimaks, kas praegune aeg on kahe aja vahel
def is_time_between(begin_time, end_time, check_time=None):
    check_time = check_time or get_current_time()
    if begin_time < end_time:
        return check_time >= begin_time and check_time <= end_time
    else:  # When the time period spans midnight / Kui ajavahemik ületab südaöö
        return check_time >= begin_time or check_time <= end_time

def detect_raspberry_pi_audio_device() -> Union[str, None]:
    logging.info("Attempting to auto-detect Raspberry Pi audio device...")
    try:
        # Try parsing 'aplay -l' output
        result = subprocess.run(['aplay', '-l'], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            lines = result.stdout.splitlines()
            # Regex to find card number, device number, and description
            # Example line: card 0: Headphones [bcm2835 Headphones], device 0: Headphones [Headphones]
            # Or: card 0: bcm2835_alsa [bcm2835 ALSA], device 0: bcm2835 ALSA [bcm2835 ALSA]
            # We are looking for hw:card,device
            device_pattern = re.compile(r"card (\d+): .*\[(.*)\].*device (\d+):")

            found_devices = []
            for line in lines:
                match = device_pattern.search(line)
                if match:
                    card_num = match.group(1)
                    description = match.group(2).lower() # Full description in brackets
                    device_num = match.group(3) # Device number for that card. Often 0 for primary.

                    # Check for keywords indicating analog/headphone output
                    # Prioritize "Headphones". Also consider "Analogue", "Analog", "bcm2835 ALSA" (common for Pi).
                    # Avoid HDMI if other options are present.
                    is_headphone = "headphones" in description
                    is_analog = "analog" in description or "analogue" in description
                    is_bcm2835 = "bcm2835" in description # Often the Pi's general audio
                    is_hdmi = "hdmi" in description

                    if is_headphone or is_analog or (is_bcm2835 and not is_hdmi):
                        device_str = f"hw:{card_num},{device_num}"
                        logging.info(f"Found potential device: {device_str} with description: {description}")
                        # Prioritize "Headphones"
                        if is_headphone:
                            found_devices.insert(0, device_str) # Add to front
                        else:
                            found_devices.append(device_str)

            if found_devices:
                selected_device = found_devices[0] # Take the best match
                logging.info(f"Auto-detected audio device from 'aplay -l': {selected_device}")
                return selected_device

        else:
            logging.warning(f"'aplay -l' command failed or returned non-zero exit code: {result.returncode}. Stderr: {result.stderr}")

    except FileNotFoundError:
        logging.warning("'aplay' command not found. Cannot auto-detect using 'aplay -l'.")
    except Exception as e:
        logging.error(f"Error during 'aplay -l' parsing: {e}")

    # Fallback to common ALSA names if 'aplay -l' fails or yields no suitable device
    logging.info("Falling back to trying common ALSA device names for Raspberry Pi.")
    common_devices = ["hw:0,0", "hw:1,0"] # Common for headphone jack on different Pi models

    for device in common_devices:
        # device string format is "hw:X,Y". We need to check for /dev/snd/pcmCXDYp
        try:
            parts = device.split(':')
            if len(parts) == 2:
                card_device = parts[1].split(',')
                if len(card_device) == 2:
                    card = card_device[0]
                    dev = card_device[1]
                    # Check for playback device file existence
                    # Standard ALSA device file: /dev/snd/pcmC{card}D{device}p (p for playback, c for capture)
                    device_path = f"/dev/snd/pcmC{card}D{dev}p"
                    if os.path.exists(device_path):
                        logging.info(f"Verified existence of fallback device: {device} (found {device_path})")
                        return device
        except Exception as e:
            logging.error(f"Error checking device existence for {device}: {e}")

    logging.warning("No common ALSA devices (hw:0,0 or hw:1,0) found via file check.")
    return None # Return None to let RadioPlayer use system default

# Function to check if the configuration file content has changed / Funktsioon kontrollimaks, kas konfiguratsioonifaili sisu on muutunud
def get_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

# Function to load audio files from a folder / Funktsioon helifailide laadimiseks kaustast
def load_audio_files(music_folder_path):
    audio_files = []
    if not os.path.isdir(music_folder_path):
        logging.warning(f"Music folder not found: {music_folder_path}")
        return audio_files
    for file in os.listdir(music_folder_path):
        if file.lower().endswith(('.mp3', '.wav')):
            audio_files.append(os.path.join(music_folder_path, file))
    if not audio_files:
        logging.warning(f"No audio files found in music folder: {music_folder_path}")
    else:
        logging.info(f"Loaded audio files: {audio_files}")
    return audio_files

# Main function / Põhifunktsioon
def main():
    config = load_config(CONFIG_PATH)  # Load the configuration file / Laadige konfiguratsioonifail
    if config is None:
        logging.error("Failed to load configuration. Exiting.")
        return

    audio_device_from_config = config.get('audio_output_device')
    audio_device = None # Initialize audio_device to None

    if audio_device_from_config and audio_device_from_config.strip(): # Check if configured and not empty
        audio_device = audio_device_from_config.strip()
        logging.info(f"Using audio output device from config file: {audio_device}")
    else:
        if 'audio_output_device' in config: # Key exists but is empty or whitespace
             logging.info("Audio output device is empty in config. Attempting auto-detection.")
        else: # Key does not exist
             logging.info("Audio output device not configured in config. Attempting auto-detection.")

        detected_device = detect_raspberry_pi_audio_device()
        if detected_device:
            audio_device = detected_device
            logging.info(f"Successfully auto-detected audio device: {audio_device}")
        else:
            logging.error("Auto-detection of audio device failed. No audio will be played. Please configure 'audio_output_device' in config.toml if you want audio output.")
            # audio_device remains None

    open_time_str, close_time_str = get_today_schedule(config)  # Get today's schedule / Saage tänane ajakava
    open_time = datetime.strptime(open_time_str, "%H:%M").time()  # Get opening time / Saage avamisaeg
    close_time = datetime.strptime(close_time_str, "%H:%M").time()  # Get closing time / Saage sulgemisaeg
    time_before_opening = config['time_before_opening']
    time_after_closing = config['time_after_closing']
    config_check_interval = config['config_check_interval']
    announcements = get_today_announcements(config)

    # Calculate start and end times based on configuration / Arvutage konfiguratsiooni põhjal algus- ja lõpuaeg
    start_time = (datetime.combine(datetime.now(), open_time) - timedelta(minutes=time_before_opening)).time()
    end_time = (datetime.combine(datetime.now(), close_time) + timedelta(minutes=time_after_closing)).time()

    logging.info(f"Initial schedule loaded: start time: {start_time}, end time: {end_time}")
    logging.info(f"Today's announcements: {announcements}")

    # 1. Start fresh logging
    enable_memory_logging = config.get('enable_memory_logging', False)
    log_memory_usage(enable_memory_logging)

    last_hash = get_file_hash(CONFIG_PATH)
    last_config_check_minute = -1

    # Initialize RadioPlayer
    radio_player = RadioPlayer(audio_device)

    last_announcement_time = None
    audio_files = [] # Initialize empty list for audio files
    file_index = 0
    current_day = datetime.now().day

    # Determine music folder path
    music_folder_path_config = config.get('background_music_folder')
    default_music_folder = os.path.join(WORKING_DIR, "bgmusic")

    if music_folder_path_config and os.path.isdir(music_folder_path_config):
        audio_files = load_audio_files(music_folder_path_config)
    elif os.path.isdir(default_music_folder):
        logging.info(f"No valid 'background_music_folder' in config, using default: {default_music_folder}")
        audio_files = load_audio_files(default_music_folder)
    else:
        logging.warning("No background music folder specified in config and default 'bgmusic' folder not found. No background music will be played.")

    while True:
        now = get_current_time()  # Get the current time / Saage praegune aeg
        now_str = now.strftime("%H:%M")
        new_day = datetime.now().day
        
        # Create a new log file if the day has changed
        if new_day != current_day:
            setup_logging()
            current_day = new_day
            logging.info(f"Day changed. Log file updated to: {LOG_FILE}")

        # Check for announcements / Kontrollige teadaandeid
        if now_str in announcements:
            announcement_file = announcements[now_str]
            if last_announcement_time != now_str:
                logging.info(f"Playing announcement: {announcement_file} at {now_str}")

                radio_player.set_volume(20)  # Reduce background music volume / Vähendage taustamuusika helitugevust

                # Ensure full path is used for announcements
                announcement_path = os.path.join(WORKING_DIR, announcement_file)
                radio_player.play_announcement(announcement_path)

                radio_player.set_volume(100)  # Restore background music volume / Taastage taustamuusika helitugevus

                last_announcement_time = now_str

        # Play background music / Mängige taustamuusikat
        if audio_files: # Only attempt to play if there are audio files loaded
            if is_time_between(start_time, end_time):
                state = radio_player.get_state()
                if state == vlc.State.Ended:
                    logging.info(f"Finished playing {audio_files[file_index]}.")
                    file_index = (file_index + 1) % len(audio_files)
                    radio_player.play_file(audio_files[file_index])
                    # 2. Logged after every audio file switch.
                    log_memory_usage(enable_memory_logging)
                elif state == vlc.State.NothingSpecial or state == vlc.State.Stopped:
                    logging.info("Within time window, starting playback.")
                    radio_player.play_file(audio_files[file_index])
                    # 2. Logged after every audio file switch (initial start).
                    log_memory_usage(enable_memory_logging)
            else:
                state = radio_player.get_state()
                if state != vlc.State.Stopped and state != vlc.State.NothingSpecial:
                     radio_player.stop()
                     # 3. Logged in every end of day when script stops playing.
                     log_memory_usage(enable_memory_logging)
        else: # No audio files loaded
            state = radio_player.get_state()
            if state != vlc.State.Stopped and state != vlc.State.NothingSpecial:
                 radio_player.stop()
                 # 3. Logged in every end of day when script stops playing.
                 log_memory_usage(enable_memory_logging)

        # Check if the configuration file content has changed at specified intervals / Kontrollige, kas konfiguratsioonifaili sisu on muutunud määratud intervallidega
        current_minute = datetime.now().minute
        if (datetime.now() - timedelta(minutes=config_check_interval)).minute % config_check_interval == 0 and current_minute != last_config_check_minute:
            last_config_check_minute = current_minute
            current_hash = get_file_hash(CONFIG_PATH)

            if current_hash != last_hash:
                config = load_config(CONFIG_PATH)  # Load the updated configuration file / Laadige uuendatud konfiguratsioonifail
                if config is None:
                    logging.error("Failed to load updated configuration. Exiting.")
                    return

                open_time_str, close_time_str = get_today_schedule(config)  # Get today's schedule / Saage tänane ajakava
                open_time = datetime.strptime(open_time_str, "%H:%M").time()
                close_time = datetime.strptime(close_time_str, "%H:%M").time()
                time_before_opening = config['time_before_opening']
                time_after_closing = config['time_after_closing']
                config_check_interval = config['config_check_interval']
                enable_memory_logging = config.get('enable_memory_logging', False) # Update memory logging setting
                announcements = get_today_announcements(config)
                start_time = (datetime.combine(datetime.now(), open_time) - timedelta(minutes=time_before_opening)).time()
                end_time = (datetime.combine(datetime.now(), close_time) + timedelta(minutes=time_after_closing)).time()
                last_hash = current_hash
                logging.info(f"Reloaded updated config file: start time: {start_time}, end time: {end_time}")
                logging.info(f"Today's announcements: {announcements}")
                
                # Check for audio device change
                audio_device_from_config = config.get('audio_output_device')
                new_audio_device = audio_device

                if audio_device_from_config and audio_device_from_config.strip():
                    new_audio_device = audio_device_from_config.strip()
                else:
                    # Auto detect again if not in config?
                    # Original code didn't auto-detect again unless it was starting up, but logically we should if we want to support switching to auto-detect.
                    # For safety, let's just stick to config value if present.
                    # If empty in config, we might want to auto-detect.
                    if 'audio_output_device' in config and not config['audio_output_device']:
                         detected = detect_raspberry_pi_audio_device()
                         if detected:
                             new_audio_device = detected

                # Update device in player
                if radio_player.update_device(new_audio_device):
                    audio_device = new_audio_device

                # Reload audio files based on new config
                music_folder_path_config = config.get('background_music_folder')
                if music_folder_path_config and os.path.isdir(music_folder_path_config):
                    audio_files = load_audio_files(music_folder_path_config)
                elif os.path.isdir(default_music_folder):
                    logging.info(f"No valid 'background_music_folder' in config, using default: {default_music_folder}")
                    audio_files = load_audio_files(default_music_folder)
                else:
                    logging.warning("No background music folder specified in config and default 'bgmusic' folder not found after config reload. No background music will be played.")
                    audio_files = [] # Ensure audio_files is empty

                # Check if we should be playing music / Kontrollige, kas peaksime muusikat mängima
                if audio_files:
                    if is_time_between(start_time, end_time):
                        state = radio_player.get_state()
                        if state == vlc.State.NothingSpecial or state == vlc.State.Stopped or state == vlc.State.Ended:
                             logging.info("Config file changed and within time window, starting/restarting playback.")
                             file_index = 0
                             radio_player.play_file(audio_files[file_index])
                    else:
                         radio_player.stop()
                else: # No audio files after config reload
                    radio_player.stop()

        time.sleep(1)  # Check frequently for state changes / Kontrollige sageli olekumuutusi

if __name__ == "__main__":
    logging.info("Starting the script.")
    while True:
        try:
            main()  # Run the main function / Käivitage põhifunktsioon
        except Exception as e:
            logging.error(f"Error: {e}")  # Log any errors / Logige kõik vead
            time.sleep(60)  # Wait before restarting in case of error / Oodake enne uuesti käivitamist vea korral
