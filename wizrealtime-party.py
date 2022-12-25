from os import system
from pywizlight import wizlight, PilotBuilder, discovery
from random import random
import asyncio
import aubio
import audioop
import math
import numpy as np
import pyaudio
import time

BULBS = []
SAMPLES = []
VOLUMES = []


def gen_color(volume, max=100):

    br = 100 + int((int(volume)*155)/int(max))
    case = int(random()*3)
    if case == 0:
        r= 255
        g= random()*24
        b= random()*24
    elif case == 1:
        r= random()*24
        g= 255
        b= random()*24
    elif case == 2:
        r= random()*24
        g= random()*24
        b= 255
    return (r,g,b, br)

def beat_detection(data, volume, threshold=50, max=100):
    if volume > threshold:
        case = int(random()*3)
        color = gen_color(volume, max)
        bulb_index = int(random()*len(BULBS))

        return{
                "case" : case ,
                "bulb" : BULBS[bulb_index],
                "color": color
        }
    else:
        return None

def get_volume(data):
    # Calculate the volume in dB
    try:
        volume = audioop.rms(data, 2)
        # volume = 20 * math.log10(volume)
        return volume
    except:
        return 0

async def light_controller(audio_input):
    # configuration
    # in seconds
    record_for      = 5
    bulb_lock_for   = 0.3 # 0.3 -> 200 bpm
    refresh_rate    = 0.001
    min_br          = 50
    
    # variables

    # initially, it is set to 100000, it will
    # be then set automatically depending on
    # how many seconds of samples you want to0
    # have record of
    _max_sample_count       = 1000000
    _tared                  = False
    _tareting               = False
    _tareting_started_at    = 0
    _vols_count             = 0
    _max_volume             = 0
    _average_volume         = 0
    _min_volume             = 0

    stop = False

    while not stop:
        data = audio_input.read(1024)

        # while tareting, nothing will happen
        if not _tared:
            if not _tareting:
                _tareting_started_at = time.time() 
                _tareting = True
            if time.time() - _tareting_started_at >= record_for:
                _tareting = False
                _tared = True
                _max_sample_count = len(SAMPLES)

        SAMPLES.append(data)
        VOLUMES.append(get_volume(data))
        
        if _tareting:
            system("clear")
            print("Tareting")
            continue

        if len(SAMPLES) > _max_sample_count:
            SAMPLES.pop(0)
            VOLUMES.pop(0)

        _max_volume = np.max(VOLUMES)
        _average_volume = np.average(VOLUMES)
        _min_volume = np.min(VOLUMES)

        system("clear")
        print("=======================")
        print(f"= Volume: {int(VOLUMES[-1])}")
        print(f"= Max: {int(_max_volume)}")
        print(f"= Average: {int(_average_volume)}")
        print(f"= Min: {int(_min_volume)}")
        print(f"= Count: {len(SAMPLES)}")
        print(f"= Tarato: {_tared}")
        print("=======================")

        beat = beat_detection(data, VOLUMES[-1], _average_volume, _max_volume)

        if beat is not None:
            on_bulb = beat["bulb"]

            # set bulb to new beat values
            if on_bulb["lock_for"] < time.time() - on_bulb["last_lock"]:
                on_bulb["lock"]         = False

            if not on_bulb["lock"]:
                on_bulb["br"]           = beat["color"][3]
                on_bulb["r"]            = beat["color"][0]
                on_bulb["g"]            = beat["color"][1]
                on_bulb["b"]            = beat["color"][2]
                on_bulb["last_lock"]    = time.time()
                on_bulb["lock"]         = True

        for bulb in BULBS:
            if bulb["br"] > min_br:
                bulb["br"] -= (256-bulb["br"])
                await bulb["light"].turn_on(PilotBuilder(
                    speed       = 200,
                    rgb         = (bulb["r"], bulb["g"], bulb["b"]),
                    brightness  = bulb["br"]
                ))
            else:
                bulb["lock"] = False
                await bulb["light"].turn_off()

        time.sleep(refresh_rate)


def main():
    # configuration
    bulbips = [
        "192.168.1.25",
        "192.168.1.29",
    ]

    input_rate          = 44100
    input_channels      = 1
    input_frames        = 1024

    # bulb init
    for ip in bulbips:
        BULBS.append({
            "light": wizlight(ip),
            "br": 255,
            "r": 255, "g": 255, "b": 255, 
            "lock_for": 0,
            "last_lock": 0,
            "lock": False
        })
    
    # microphone socket init
    audio_input = pyaudio.PyAudio().open(
            format              = pyaudio.paInt16,
            rate                = input_rate,
            channels            = input_channels,
            frames_per_buffer   = input_frames,
            input               = True,
    )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(light_controller(audio_input))
    
if __name__ == "__main__":
    main()
