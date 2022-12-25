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

BULBIPS = ["192.168.1.25", "192.168.1.29"]

def __gen_color_standard(seed):
    case = int(seed%3)
    br = 200+int(seed%55)
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



def gen_color(seed, mode="standard"):
    match mode:
        case "standard":
            return __gen_color_standard(seed)
        case "dynamic":
            return __gen_color_standard(seed)
        case _:
            return __gen_color_standard(seed)

def __onset_specdiff(ws, hs, src_func, duration):
    onsetfunc = onset('specdiff', ws, hs)
    onset_times = []
    while True: # read frames
       samples, num_frames_read = src_func()
       if onsetfunc(samples):
           onset_time = onsetfunc.get_last_s()
           if onset_time < duration:
                case = int(onset_time*1000%3)
                color = gen_color(onset_time*1000)
                onset_times.append([onset_time, case, int(random()*len(BULBIPS)), color ])
           else:
                break
       if num_frames_read < hs:
           break
    onset_times.sort()
    return onset_times

def __onset_dynamic(ws, hs, src_func, duration, sr=0):
    # bpm detection -> when
    beats = []
    total_frames = 0
    o = tempo("specdiff", ws, hs, sr,)
    while True:
        samples, read = src_func()
        is_beat = o(samples)
        print(f"{total_frames} : {hs}")
        if is_beat:
            this_beat = o.get_last_s()
            beats.append(this_beat)
        total_frames += read
        if read < hs:
            break
    print(beats)
    def beats_to_bpm(beats):
        # if enough beats are found, convert to periods then to bpm
        if len(beats) > 1:
            if len(beats) < 4:
                bpms = 60./diff(beats)
            return median(bpms)
        else:
            return 0

    bpm = beats_to_bpm(beats)

    # energy detection -> brightness
    gap = duration / bpm
    onset_times = []
    onset_time = 0
    while onset_time < duration: # read frames
        case = int(onset_time*1000%3)
        color = gen_color(onset_time*1000)
        onset_times.append([onset_time, case, int(random()*len(BULBIPS)), color ])
        onset_time += gap

    onset_times.sort()

    return onset_times


def onset_detection(file_path, mode="specdiff", ws=1024, hs=0, sr=0):
    if hs == 0:
        hop_size = ws // 1

    src_func = source(file_path, sr, hs)
    sample_rate = src_func.samplerate
    duration = float(src_func.duration) / src_func.samplerate

    match mode:
        case "specdiff":
            return __onset_specdiff(ws, hop_size, src_func, duration)
        case "dynamic":
            return __onset_dynamic(ws, hop_size, src_func, duration)
        case _:
            pass


async def main():
    if len(argv) < 2:
        print("specify the path of a song")
        exit(1)
    # path to audio file
    file_path = argv[1]

    # init bulbs
    bulbs = []
    for bulb in BULBIPS:
        bulbs.append({"light": wizlight(bulb), "br": 255, "r":0, "g":0, "b":0})

    onset_times = onset_detection(file_path, ws=512, mode="specdiff")

    mixer.init()
    mixer.music.load(file_path)
    mixer.music.play()
    # play
    while len(onset_times) > 0:
        current_time = mixer.music.get_pos()/1000

        system("clear")
        print("=======================")
        print(f"= Elapsed time: {str(current_time).split('.')[0]}")
        print(f"= Title: {file_path.split('/')[-1]}")
        print("=======================")

        beat = onset_times[0]

        if  beat[0] <= current_time:
            on_bulb = beat[2]
            bulbs[on_bulb]["br"] = beat[3][3]
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
