import pywizlight
import pyaudio
import wave
import audioop
import math
import asyncio

async def turn_on_lights():
    global LOCK_ON
    global LOCK_OFF
    if not LOCK_ON:
        # Connect to the WiZ lights
        first = pywizlight.wizlight("192.168.1.16")
        second = pywizlight.wizlight("192.168.1.25")
        # Turn on the lights
        await first.turn_on()
        await second.turn_on()
        LOCK_ON = True
        LOCK_OFF = False

async def turn_off_lights():
    global LOCK_ON
    global LOCK_OFF
    if not LOCK_OFF:
        # Connect to the WiZ lights
        first = pywizlight.wizlight("192.168.1.16")
        second = pywizlight.wizlight("192.168.1.25")
        # Turn on the lights
        await first.turn_off()
        await second.turn_off()
        LOCK_ON = False
        LOCK_OFF = True

def get_volume(data):
    # Calculate the volume in dB
    volume = audioop.rms(data, 2)
    volume = 20 * math.log10(volume)
    return volume

async def main():
    p = pyaudio.PyAudio()
    THRESHOLD = 50

    # Set up a stream to read from the microphone
    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=44100,
                    input=True,
                    frames_per_buffer=1024)
    
    while True:
        data = stream.read(1024)

        volume = get_volume(data)

        if volume > THRESHOLD:
            await turn_on_lights()
        else:
            await turn_off_lights()

LOCK_ON = False
LOCK_OFF = False
loop = asyncio.get_event_loop()
loop.run_until_complete(main())
