import asyncio
import time
from sys import argv
from aubio import source, onset, tempo, pitch
from numpy import median, diff
from pygame import mixer
from os import system
from random import random
import threading
from pywizlight import wizlight, PilotBuilder, discovery

def __gen_color_standard(seed):
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
    return (r,g,b)



async def gen_color(seed, mode="standard"):
    match mode:
        case "standard":
            return __gen_color_standard(seed)
        case _:
            return __gen_color_standard(seed)

def __onset_specdiff(ws, hs, src_func):
    onsetfunc = onset('specdiff', ws, hs)
    onset_times = []
    while True: # read frames
       samples, num_frames_read = src_func()
       if onsetfunc(samples):
           onset_time = onset_specdiff.get_last_s()
           if onset_time < duration:
               case = int(onset_time*1000%3)
               onset_times.append([onset_time, case, int(random()*len(bulbips)), await gen_color(case)])
           else:
               break
       if num_frames_read < hop_size:
           break
    onset_times.sort()
    return onset_times


async def onset_detection(file_path, mode, ws=1024, hs=0, sr=0):
    if hs == 0:
        hop_size = window_size // 1

    src_func = source(file_path, sr, hs)
    sample_rate = src_func.samplerate
    duration = float(src_func.duration) / src_func.samplerate

    match mode:
        case "specdiff":
            __onset_specdiff(ws, hs)
        case pattern_2:
            pass


async def main():
    if len(argv) < 2:
        print("specify the path of a song")
        exit(1)

    file_path = argv[1]
    time_begin = time.time()
    mixer.init()
    mixer.music.load(file_path)



    bulbips = ["192.168.1.14", "192.168.1.2"]


    bulbs = []
    for bulb in bulbips:
        bulbs.append({"light": wizlight(bulb), "br": 255, "r":0, "g":0, "b":0})

    on_bulb = random()*len(bulbips)


    mixer.music.play()
    while len(onset_times) > 0:
        current_time = mixer.music.get_pos()/1000
        #print("\033c", end='')
        system("clear")
        print(f"Current time: {str(current_time).split('.')[0]}")
        print("Beat: " + str(onset_times[0]))
        print("Remaining: " + str(len(onset_times)))
        print("=======================")
        beat = onset_times[0]

        if  beat[0] <= current_time:
        #    case = beat[1]
        #    on_bulb = beat[2]

        #    onset_times.pop(0)

        #    bulbs[on_bulb]["br"] = 255
        #    if case == 0:
        #        bulbs[on_bulb]["r"] = 255
        #        bulbs[on_bulb]["g"] = random()*150
        #        bulbs[on_bulb]["b"] = random()*150
        #    elif case == 1:
        #        bulbs[on_bulb]["r"] = random()*150
        #        bulbs[on_bulb]["g"] = 255
        #        bulbs[on_bulb]["b"] = random()*150
        #    elif case == 2:
        #        bulbs[on_bulb]["r"] = random()*150
        #        bulbs[on_bulb]["g"] = random()*150
        #        bulbs[on_bulb]["b"] = 255
            on_bulb = beat[2]
            bulbs[on_bulb]["br"] = 255
            bulbs[on_bulb]["r"] = beat[3][0]
            bulbs[on_bulb]["g"] = beat[3][1]
            bulbs[on_bulb]["b"] = beat[3][2]
            onset_times.pop(0)

        for bulb in bulbs:
            if bulb["br"] > 0:
                bulb["br"] -= (256-bulb["br"])
                await bulb["light"].turn_on(PilotBuilder(
                    speed=200,
                    rgb=(bulb["r"], bulb["g"], bulb["b"]),
                    brightness=bulb["br"]
                ))
            else:
                await bulb["light"].turn_off()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
