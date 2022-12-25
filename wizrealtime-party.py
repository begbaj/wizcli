import asyncio
import time
from sys import argv
from aubio import source, onset, tempo, pitch
from numpy import median, diff
import numpy as np
from os import system
from random import random
import threading
from pywizlight import wizlight, PilotBuilder, discovery
import pyaudio
import audioop
import math

def gen_color(case, volume=-1, max=100, min=0):
    if volume == -1:
        br = 255
    else:
        br = 100 + int((int(volume)*155)/int(max))
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

def onset_detection(stream_data, samplerate, volume, threshold=70, max=100):
    global bulbs
    onset_method = 'specflux'
    buf_size = 2048
    hop_size = buf_size // 2

    onsetfunc = onset(onset_method, buf_size, hop_size, samplerate)

    samples = np.fromstring(stream_data, dtype=np.int16)
    samples = samples.reshape((-1,))
    samples = samples.astype(np.float32)

    if volume > threshold and onsetfunc(samples):
        onset_time = onsetfunc.get_last_s()
        case = int(random()*3)
        color = gen_color(case, volume, max)
        return [onset_time, case, int(random()*len(bulbs)), color ]
    else:
        return [None, 0, int(random()*len(bulbs)), (0,0,0,0) ]

def get_volume(data):
    # Calculate the volume in dB
    try:
        volume = audioop.rms(data, 2)
        # volume = 20 * math.log10(volume)
        return volume
    except:
        return 0

async def main():
    # init bulbs
    global bulbs
    # with open("bulbs.txt") as f:
    #    for bulb in f.readlines():
    #        print(bulb)
    #        bulbs.append({"light": wizlight(bulb), "br": 255, "r":0, "g":0, "b":0})

    p = pyaudio.PyAudio()

    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=44100,
                    input=True,
                    frames_per_buffer=1024)
    
    volumes = []
    volumes_count = 0
    max_volumes = 1000000
    tarato = False
    tarating = False
    avarage_of_last_seconds = 15
    start_tarating = 0
    lock_for = 0.3 # max 200 bpm
    refresh_rate = 0.001

    bulbs.append({"light": wizlight("192.168.1.25"), "br": 255, "r":0, "g":0, "b":0, "lock_for": lock_for, "last_lock": time.time(), "state": 0})
    # bulbs.append({"light": wizlight("192.168.1.29"), "br": 255, "r":0, "g":0, "b":0, "lock_for": lock_for, "last_lock": time.time(), "state": 0})
    max = 0
    average = 0
    min = 0

    while True:
        stream_data = stream.read(1024)
        volume = get_volume(stream_data)

             
        if volume > 0:
            volumes.append(int(volume))
            volumes_count += 1
            if not tarato:
                if not tarating:
                   start_tarating = time.time() 
                tarating = True
                if time.time() - start_tarating >= avarage_of_last_seconds:
                    tarating = False
                    tarato = True
                    max_volumes = volumes_count
        else:
            tarato = False
            volumes = []
            volumes_count = 0
        if volumes_count > max_volumes:
            volumes.pop(0)
            volumes_count -= 1

        # if len(volumes) > 10000:
        #    volumes.pop(0)
        if volumes_count > 0:
            max = np.max(volumes)
            average = np.average(volumes)
            min = np.min(volumes)
            if (max - min) < 3:
                volume = 0
        else:
            average = 1
            volume = 0

        beat = onset_detection(stream_data, 44100, volume, average, max)

        on_bulb = beat[2]
        if bulbs[on_bulb]["lock_for"] < time.time() - bulbs[on_bulb]["last_lock"] and bulbs[on_bulb]["br"] <= 5 and bulbs[on_bulb]["state"] == 0:
            bulbs[on_bulb]["br"] = beat[3][3]
            bulbs[on_bulb]["r"] = beat[3][0]
            bulbs[on_bulb]["g"] = beat[3][1]
            bulbs[on_bulb]["b"] = beat[3][2]
            bulbs[on_bulb]["last_lock"] = time.time()

        system("clear")
        print("=======================")
        print(f"= Volume: {int(volume)}")
        print(f"= Max: {int(max)}")
        print(f"= Average: {int(average)}")
        print(f"= Min: {int(min)}")
        print(f"= Count: {volumes_count}")
        print(f"= Tarato: {tarato}")
        print("=======================")

        for bulb in bulbs:
            if bulb["br"] > 0:
                bulb["br"] -= (256-bulb["br"])
                bulb["state"] = 1
                await bulb["light"].turn_on(PilotBuilder(
                    speed=200,
                    rgb=(bulb["r"], bulb["g"], bulb["b"]),
                    brightness=bulb["br"]
                ))
            else:
                if bulb["state"]:
                    bulb["state"] = 0
                    await bulb["light"].turn_off()
        time.sleep(refresh_rate)

bulbs = []
loop = asyncio.get_event_loop()
loop.run_until_complete(main())
