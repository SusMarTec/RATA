# -*- coding: utf-8 -*-
import toml
import time
from datetime import datetime, timedelta
import vlc
import os
import logging
import hashlib

# Määrab konfiguratsioonifaili ja logifaili asukoha
WORKING_DIR = os.path.expanduser("~/Radio")
CONFIG_PATH = os.path.join(WORKING_DIR, "config.toml")
LOG_DIR = os.path.join(WORKING_DIR, "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
LOG_FILE = os.path.join(LOG_DIR, datetime.now().strftime("%m%d%Y") + ".log")
AUDIO_FILES = ["sc1.mp3", "sc2.mp3", "sc3.mp3"]
RESTART_INTERVAL = 24 * 60 * 60

# Konfigureerib logimise
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Funktsioon konfiguratsioonifaili laadimiseks
def load_config(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return toml.load(f)

# Funktsioon praeguse aja saamiseks
def get_current_time():
    return datetime.now().time()

# Funktsioon, mis määrab tänase päeva ajad
def get_today_schedule(config):
    default_open_time = config['default_open_time']
    default_close_time = config['default_close_time']
    today = datetime.today().strftime('%A').lower()  # Saab tänase päeva nime

    schedule = config['weekly_schedule'].get(today, {})
    open_time = schedule.get('open_time', default_open_time)
    close_time = schedule.get('close_time', default_close_time)

    return open_time, close_time

# Funktsioon, mis kontrollib, kas antud aeg jääb kahe aja vahele
def is_time_between(begin_time, end_time, check_time=None):
    check_time = check_time or get_current_time()
    if begin_time < end_time:
        return check_time >= begin_time and check_time <= end_time
    else:  # Kui ajavahemik ületab südaöö
        return check_time >= begin_time or check_time <= end_time

# Funktsioon üksiku audiofaili mängimiseks
def play_audio(file):
    file_path = os.path.join(WORKING_DIR, file)
    instance = vlc.Instance('--aout=alsa', '--alsa-audio-device=hw:2,0')  # Seadistab VLC kasutama konkreetset ALSA seadet (bcm2835 Headphones)
    player = instance.media_player_new()
    media = instance.media_new(file_path)
    player.set_media(media)
    player.play()
    logging.info(f"Started playing {file_path}.")
    return player

# Funktsioon audio peatamiseks
def stop_audio(player):
    if player:
        player.stop()
        logging.info("Stopped playing audio file.")

# Funktsioon konfiguratsioonifaili sisu muutuse kontrollimiseks
def get_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

# Peamine funktsioon
def main():
    config = load_config(CONFIG_PATH)  # Laadib konfiguratsioonifaili
    open_time_str, close_time_str = get_today_schedule(config)  # Saab tänase päeva ajad
    open_time = datetime.strptime(open_time_str, "%H:%M").time()  # Saab poe avamisaja
    close_time = datetime.strptime(close_time_str, "%H:%M").time()  # Saab poe sulgemisaja
    time_before_opening = config['time_before_opening']
    time_after_closing = config['time_after_closing']
    config_check_interval = config['config_check_interval']
    
    # Arvutab aja vastavalt konfiguratsioonifailile
    start_time = (datetime.combine(datetime.now(), open_time) - timedelta(minutes=time_before_opening)).time()
    end_time = (datetime.combine(datetime.now(), close_time) + timedelta(minutes=time_after_closing)).time()
    
    last_hash = get_file_hash(CONFIG_PATH)
    player = None

    while True:
        now = datetime.now().time()  # Saab praeguse aja
        logging.info(f"Current time: {now}, start time: {start_time}, end time: {end_time}")
        if is_time_between(start_time, end_time):
            if player is None:
                logging.info("Within time window, starting playback.")
                for file in AUDIO_FILES:
                    if is_time_between(start_time, end_time):
                        player = play_audio(file)  # Mängib audiofaili
                        while player and player.get_state() != vlc.State.Ended:
                            if not is_time_between(start_time, end_time):
                                stop_audio(player)
                                player = None
                                break
                            time.sleep(1)
                    else:
                        break
        else:
            if player is not None:
                stop_audio(player)
                player = None
        
        # Kontrolli, kas konfiguratsioonifaili sisu on muutunud
        current_hash = get_file_hash(CONFIG_PATH)
        if current_hash != last_hash:
            config = load_config(CONFIG_PATH)  # Laadib uuendatud konfiguratsioonifaili
            open_time_str, close_time_str = get_today_schedule(config)  # Saab tänase päeva ajad
            open_time = datetime.strptime(open_time_str, "%H:%M").time()
            close_time = datetime.strptime(close_time_str, "%H:%M").time()
            time_before_opening = config['time_before_opening']
            time_after_closing = config['time_after_closing']
            config_check_interval = config['config_check_interval']
            start_time = (datetime.combine(datetime.now(), open_time) - timedelta(minutes=time_before_opening)).time()
            end_time = (datetime.combine(datetime.now(), close_time) + timedelta(minutes=time_after_closing)).time()
            last_hash = current_hash
            logging.info("Reloaded updated config file.")
            # Kontrollime, kas peaksime muusikat mängima
            if is_time_between(start_time, end_time) and player is None:
                logging.info("Config file changed and within time window, starting playback.")
                for file in AUDIO_FILES:
                    if is_time_between(start_time, end_time):
                        player = play_audio(file)
                        while player and player.get_state() != vlc.State.Ended:
                            if not is_time_between(start_time, end_time):
                                stop_audio(player)
                                player = None
                                break
                            time.sleep(1)
                    else:
                        break
            elif not is_time_between(start_time, end_time) and player is not None:
                stop_audio(player)
                player = None
        else:
            logging.info("Checked config file, no changes found.")
        
        time.sleep(config_check_interval * 60)  # Kontrollib määratud intervalli järel uuesti

if __name__ == "__main__":
    start_time = time.time()  # Salvestab skripti käivitamise aja
    logging.info("Starting the script.")
    while True:
        try:
            main()  # Käivitab peamise funktsiooni
        except Exception as e:
            logging.error(f"Error: {e}")  # Logib veateate, kui tekib viga
            time.sleep(60)  # Ootab enne taaskäivitamist vea korral
        if time.time() - start_time > RESTART_INTERVAL:
            logging.info("Restarting the script.")
            break  # Taaskäivitab skripti määratud intervalli järel
