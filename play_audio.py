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
from typing import Optional

# Define working directories and file paths / Määrake töökaustad ja failiteed
WORKING_DIR = os.path.expanduser("~/Radio")
CONFIG_PATH = os.path.join(WORKING_DIR, "config.toml")
LOG_DIR = os.path.join(WORKING_DIR, "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
# LOG_FILE global variable: Its role changes. It will be updated by setup_logging.
# Initialize it here for clarity, though setup_logging will define its operational value.
LOG_FILE = os.path.join(LOG_DIR, datetime.now().strftime("%m%d%Y") + ".log") 
AUDIO_FILES = ["sc1.mp3", "sc2.mp3", "sc3.mp3"]
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

def detect_raspberry_pi_audio_device() -> Optional[str]:
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
    # Note: Without 'aplay -l', we can't be sure these exist or are headphones.
    # For this implementation, we'll just return the first one as a guess.
    # A more robust check would involve trying to query these devices.
    # However, for now, we'll just pick the first as a last resort fallback.
    # A user should ideally configure explicitly if aplay -l fails.
    logging.warning(f"Attempting to use common device: {common_devices[0]} as a fallback. This is a guess.")
    return common_devices[0] # Return the first common device as a last attempt

    # If all detection methods fail:
    # logging.warning("Auto-detection failed to find any suitable audio device.")
    # return None # Original plan was to return None if all fails.
                  # The user feedback suggested continuing, implying we might not play audio.
                  # The fallback to common_devices[0] is a compromise.
                  # If this is also not desired, change to `return None`.

# Function to play a single audio file / Funktsioon ühe heli faili mängimiseks
def play_audio(file, audio_device_name, volume=100):
    if not audio_device_name: # Handles None or empty string
        logging.error("Audio device not determined (neither configured nor auto-detected). Cannot initialize player or play audio.")
        return None, None # Return None for both player and instance
    file_path = os.path.join(WORKING_DIR, file)
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return None, None
    instance = vlc.Instance('--aout=alsa', f'--alsa-audio-device={audio_device_name}')  # Set VLC to use specific ALSA device
    player = instance.media_player_new()
    media = instance.media_new(file_path)
    player.set_media(media)
    player.audio_set_volume(volume)  # Set the volume here / Määrake siin helitugevus
    player.play()
    logging.info(f"Started playing {file_path} with volume {volume}.")
    
    return player, instance

# Function to stop audio playback / Funktsioon heli taasesituse peatamiseks
def stop_audio(player, instance):
    if player:
        player.stop()
        player.release()
        instance.release()
        logging.info("Stopped playing audio file and released the player.")

# Function to check if the configuration file content has changed / Funktsioon kontrollimaks, kas konfiguratsioonifaili sisu on muutunud
def get_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

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

    last_hash = get_file_hash(CONFIG_PATH)
    player = None
    instance = None
    last_announcement_time = None

    file_index = 0
    current_day = datetime.now().day

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
                if player:
                    player.audio_set_volume(20)  # Reduce background music volume / Vähendage taustamuusika helitugevust
                announcement_player, announcement_instance = play_audio(announcement_file, audio_device, volume=100)  # Play announcement at full volume / Mängige teadaanne täieliku helitugevusega
                while announcement_player.get_state() != vlc.State.Ended:
                    time.sleep(1)
                stop_audio(announcement_player, announcement_instance)
                if player:
                    player.audio_set_volume(100)  # Restore background music volume / Taastage taustamuusika helitugevus
                last_announcement_time = now_str

        # Play background music / Mängige taustamuusikat
        if is_time_between(start_time, end_time):
            if player is None:
                logging.info("Within time window, starting playback.")
                player, instance = play_audio(AUDIO_FILES[file_index], audio_device)
            elif player.get_state() == vlc.State.Ended:
                logging.info(f"Finished playing {AUDIO_FILES[file_index]}.")
                stop_audio(player, instance)
                file_index = (file_index + 1) % len(AUDIO_FILES)
                player, instance = play_audio(AUDIO_FILES[file_index], audio_device)
        else:
            if player is not None:
                stop_audio(player, instance)
                player = None
                instance = None

        # Check if the configuration file content has changed at specified intervals / Kontrollige, kas konfiguratsioonifaili sisu on muutunud määratud intervallidega
        if (datetime.now() - timedelta(minutes=config_check_interval)).minute % config_check_interval == 0:
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
                announcements = get_today_announcements(config)
                start_time = (datetime.combine(datetime.now(), open_time) - timedelta(minutes=time_before_opening)).time()
                end_time = (datetime.combine(datetime.now(), close_time) + timedelta(minutes=time_after_closing)).time()
                last_hash = current_hash
                logging.info(f"Reloaded updated config file: start time: {start_time}, end time: {end_time}")
                logging.info(f"Today's announcements: {announcements}")
                
                # Check if we should be playing music / Kontrollige, kas peaksime muusikat mängima
                if is_time_between(start_time, end_time) and (player is None or player.get_state() == vlc.State.Ended):
                    logging.info("Config file changed and within time window, starting playback.")
                    file_index = 0
                    player, instance = play_audio(AUDIO_FILES[file_index], audio_device)
                elif not is_time_between(start_time, end_time) and player is not None:
                    stop_audio(player, instance)
                    player = None
                    instance = None

        time.sleep(1)  # Check frequently for state changes / Kontrollige sageli olekumuutusi

if __name__ == "__main__":
    logging.info("Starting the script.")
    while True:
        try:
            main()  # Run the main function / Käivitage põhifunktsioon
        except Exception as e:
            logging.error(f"Error: {e}")  # Log any errors / Logige kõik vead
            time.sleep(60)  # Wait before restarting in case of error / Oodake enne uuesti käivitamist vea korral
