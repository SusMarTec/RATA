# -*- coding: utf-8 -*-
import toml
import time
from datetime import datetime, timedelta
import vlc
import os
import logging
import hashlib

# Define working directories and file paths
WORKING_DIR = os.path.expanduser("~/Radio")
CONFIG_PATH = os.path.join(WORKING_DIR, "config.toml")
LOG_DIR = os.path.join(WORKING_DIR, "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
LOG_FILE = os.path.join(LOG_DIR, datetime.now().strftime("%m%d%Y") + ".log")
AUDIO_FILES = ["sc1.mp3", "sc2.mp3", "sc3.mp3"]
RESTART_INTERVAL = 24 * 60 * 60

# Configure logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Function to load configuration file
def load_config(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config = toml.load(f)
        logging.info("Configuration file loaded successfully.")
        return config
    except Exception as e:
        logging.error(f"Error loading configuration file: {e}")
        return None

# Function to get current time
def get_current_time():
    return datetime.now().replace(microsecond=0).time()

# Function to determine today's schedule
def get_today_schedule(config):
    default_open_time = config['default_open_time']
    default_close_time = config['default_close_time']
    today = datetime.today().strftime('%A').lower()  # Get today's day name

    schedule = config['weekly_schedule'].get(today, {})
    open_time = schedule.get('open_time', default_open_time)
    close_time = schedule.get('close_time', default_close_time)

    return open_time, close_time

# Function to determine today's announcements
def get_today_announcements(config):
    default_announcements = config.get('default_announcements', {})
    today = datetime.today().strftime('%A').lower()  # Get today's day name

    announcements = config.get('announcements', {}).get(today, default_announcements)
    if not announcements:
        announcements = default_announcements
    return announcements

# Function to check if the current time is between two times
def is_time_between(begin_time, end_time, check_time=None):
    check_time = check_time or get_current_time()
    if begin_time < end_time:
        return check_time >= begin_time and check_time <= end_time
    else:  # When the time period spans midnight
        return check_time >= begin_time or check_time <= end_time

# Function to play a single audio file
def play_audio(file, volume=100):
    file_path = os.path.join(WORKING_DIR, file)
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return None
    instance = vlc.Instance('--aout=alsa', '--alsa-audio-device=hw:2,0')  # Set VLC to use specific ALSA device (bcm2835 Headphones)
    player = instance.media_player_new()
    media = instance.media_new(file_path)
    player.set_media(media)
    player.audio_set_volume(volume)  # Set the volume here
    player.play()
    logging.info(f"Started playing {file_path} with volume {volume}.")
    return player

# Function to stop audio playback
def stop_audio(player):
    if player:
        player.stop()
        logging.info("Stopped playing audio file.")

# Function to check if the configuration file content has changed
def get_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

# Main function
def main():
    config = load_config(CONFIG_PATH)  # Load the configuration file
    if config is None:
        logging.error("Failed to load configuration. Exiting.")
        return

    open_time_str, close_time_str = get_today_schedule(config)  # Get today's schedule
    open_time = datetime.strptime(open_time_str, "%H:%M").time()  # Get opening time
    close_time = datetime.strptime(close_time_str, "%H:%M").time()  # Get closing time
    time_before_opening = config['time_before_opening']
    time_after_closing = config['time_after_closing']
    config_check_interval = config['config_check_interval']
    announcements = get_today_announcements(config)

    # Calculate start and end times based on configuration
    start_time = (datetime.combine(datetime.now(), open_time) - timedelta(minutes=time_before_opening)).time()
    end_time = (datetime.combine(datetime.now(), close_time) + timedelta(minutes=time_after_closing)).time()

    logging.info(f"Initial schedule loaded: start time: {start_time}, end time: {end_time}")
    logging.info(f"Today's announcements: {announcements}")

    last_hash = get_file_hash(CONFIG_PATH)
    player = None
    last_announcement_time = None

    file_index = 0
    while True:
        now = get_current_time()  # Get the current time
        now_str = now.strftime("%H:%M")
        
        # Check for announcements
        if now_str in announcements:
            announcement_file = announcements[now_str]
            if last_announcement_time != now_str:
                logging.info(f"Playing announcement: {announcement_file} at {now_str}")
                if player:
                    player.audio_set_volume(20)  # Reduce background music volume
                announcement_player = play_audio(announcement_file, volume=100)  # Play announcement at full volume
                while announcement_player and announcement_player.get_state() != vlc.State.Ended:
                    time.sleep(1)
                stop_audio(announcement_player)
                if player:
                    player.audio_set_volume(100)  # Restore background music volume
                last_announcement_time = now_str

        # Play background music
        if is_time_between(start_time, end_time):
            if player is None:
                logging.info("Within time window, starting playback.")
            if player is None or player.get_state() == vlc.State.Ended:
                player = play_audio(AUDIO_FILES[file_index])
                file_index = (file_index + 1) % len(AUDIO_FILES)
        else:
            if player is not None:
                stop_audio(player)
                player = None

        # Check if the configuration file content has changed
        current_hash = get_file_hash(CONFIG_PATH)
        if current_hash != last_hash:
            config = load_config(CONFIG_PATH)  # Load the updated configuration file
            if config is None:
                logging.error("Failed to load updated configuration. Exiting.")
                return

            open_time_str, close_time_str = get_today_schedule(config)  # Get today's schedule
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
            
            # Check if we should be playing music
            if is_time_between(start_time, end_time) and (player is None or player.get_state() == vlc.State.Ended):
                logging.info("Config file changed and within time window, starting playback.")
                file_index = 0
                player = play_audio(AUDIO_FILES[file_index])
                file_index = (file_index + 1) % len(AUDIO_FILES)
            elif not is_time_between(start_time, end_time) and player is not None:
                stop_audio(player)
                player = None

        time.sleep(config_check_interval * 60)  # Check again after the specified interval

if __name__ == "__main__":
    start_time = time.time()  # Record the script start time
    logging.info("Starting the script.")
    while True:
        try:
            main()  # Run the main function
        except Exception as e:
            logging.error(f"Error: {e}")  # Log any errors
            time.sleep(60)  # Wait before restarting in case of error
        if time.time() - start_time > RESTART_INTERVAL:
            logging.info("Restarting the script.")
            break  # Restart the script after the specified interval
