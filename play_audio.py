# -*- coding: utf-8 -*-
import json
import time
from datetime import datetime, timedelta
import vlc
import os
import logging

# Määrab konfiguratsioonifaili ja logifaili asukoha
WORKING_DIR = os.path.expanduser("~/Radio")
CONFIG_PATH = os.path.join(WORKING_DIR, "config.json")
LOG_FILE = os.path.join(WORKING_DIR, "radio.log")
AUDIO_FILES = ["sc1.mp3", "sc2.mp3", "sc3.mp3"]
RESTART_INTERVAL = 24 * 60 * 60

# Konfigureerib logimise
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

# Funktsioon konfiguratsioonifaili laadimiseks
def load_config(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# Funktsioon praeguse aja saamiseks
def get_current_time():
    return datetime.now().time()

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
    while True:
        state = player.get_state()
        if state == vlc.State.Ended:
            logging.info(f"Finished playing {file_path}.")
            break
        time.sleep(1)
    return player

# Peamine funktsioon
def main():
    config = load_config(CONFIG_PATH)  # Laadib konfiguratsioonifaili
    open_time = datetime.strptime(config['open_time'], "%H:%M").time()  # Saab poe avamisaja
    close_time = datetime.strptime(config['close_time'], "%H:%M").time()  # Saab poe sulgemisaja

    # Arvutab aja 15 minutit enne poe avamist ja 15 minutit pärast poe sulgemist
    start_time = (datetime.combine(datetime.now(), open_time) - timedelta(minutes=15)).time()
    end_time = (datetime.combine(datetime.now(), close_time) + timedelta(minutes=15)).time()

    while True:
        now = datetime.now()  # Saab praeguse kuupäeva ja aja
        if is_time_between(start_time, end_time):
            for file in AUDIO_FILES:
                play_audio(file)  # Mängib audiofaili
                if not is_time_between(start_time, end_time):
                    break  # Kui ajavahemik on lõppenud, lõpetab tsükli
        time.sleep(60)  # Kontrollib iga minut, kas peaks alustama või lõpetama

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
