from pywizlight import wizlight, PilotBuilder, discovery
import time
import cv2
import numpy as np
import pyautogui
import time
import asyncio

BULBIPS = ["192.168.1.3"]
SCREEN_SIZE = (1920, 1080)


# Fast way to determine most dominant color, reducing to a single pixel and seeing
def get_dominant_color(pil_img):
    img = pil_img.copy()
    img = img.convert("RGBA")
    # WARNING: this only gets the central pixel
    # not the most dominant color
    img = img.resize((1, 1), resample=0)
    dominant_color = img.getpixel((0, 0))
    return dominant_color


async def main():
    bulbs = []
    for bulb in BULBIPS:
        bulbs.append({"light": wizlight(bulb), "br": 255, "r":0, "g":0, "b":0})

    fps = 30
    prev = 0

    while True:
        time_elapsed = time.time()-prev
        if time_elapsed > 1.0/fps:
            prev = time.time()

            img = pyautogui.screenshot()
            # Useful to see what pyautogui is actually capturing
            #img.save("pa.png")
            #frame = np.array(img)
            #frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            #cv2.imshow("OpenCV/Numpy normal", frame)

            color = get_dominant_color(img)

            # Another approach to find dominant color, but it's way too slow
            #color_thief = ColorThief("temporary_screenshot.png")
            #dominant_color = color_thief.get_color(quality=1)

            print("Updating bulb")
            print(color)

            for bulb in bulbs:
                await bulb["light"].turn_on(PilotBuilder(
                    speed=200,
                    rgb=(color[0],color[1],color[2]),
                    brightness=((color[0]+color[1]+color[2])/768)*255
                ))



if __name__ == "__main__":
    asyncio.run(main())
