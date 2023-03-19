from pywizlight import wizlight, PilotBuilder, discovery

from collections import Counter
from PIL import Image, ImageFilter
import random
import asyncio
import cv2
import colorsys
import numpy as np
import pyautogui
import time

BULBIPS = ["192.168.1.11","192.168.1.24"]
SCREEN_SIZE = (1920, 1080)


# Fast way to determine most dominant color, reducing to a single pixel and seeing
def get_dominant(image, precision=5):
    # Open the image and convert it to RGB format
    # image = pil_img.convert('RGB')
    # Resize the image to reduce processing time
    image = image.resize((500, 500))
    image = Image.frombytes('RGB', image.size, image.tobytes())
    image = image.filter(ImageFilter.GaussianBlur(radius=10))
    # image.save("pa.png")
    # Convert the image to a numpy array
    image_array = np.array(image)
    # Reshape the array to a list of RGB values
    pixel_list = image_array.reshape(-1, 3)
    # Get the most common colors in the image
    color_counts = Counter(map(tuple, pixel_list))
    most_common = color_counts.most_common(precision)

    color = [0,0,0]
    total = 0
    print(most_common)
    
    for c in most_common:
        color[0] += c[0][0] * c[1]
        color[1] += c[0][1] * c[1]
        color[2] += c[0][2] * c[1]
        total += c[1]
    color[0] = int(color[0]/total)
    color[1] = int(color[1]/total)
    color[2] = int(color[2]/total)

    return color


async def main():
    bulbs = []
    for bulb in BULBIPS:
        bulbs.append({"light": wizlight(bulb), "br": 255, "r":0, "g":0, "b":0})

    # fps = 60
    prev = 0

    while True:
        # time_elapsed = time.time()-prev
        # if time_elapsed > 1.0/fps:
            # prev = time.time()
            img = pyautogui.screenshot(region=(SCREEN_SIZE[0],0,SCREEN_SIZE[0],SCREEN_SIZE[1]))
            # img = pyautogui.screenshot()
            # Useful to see what pyautogui is actually capturing
            # img.save("pa.png")
            # frame = np.array(img)
            # frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # cv2.imshow("OpenCV/Numpy normal", frame)
            colors = get_dominant(img,10)

            min_sat = 1
            min_value = 0.9

            h,s,v = colorsys.rgb_to_hsv(colors[0]/255, colors[1]/255, colors[2]/255)

            print(f"original HSV: {[h,s,v]}")

            s = min_sat+(s)*(1-min_sat)
            v = min_value+(v)*(1-min_value)

            print(f"altered HSV: {[h,s,v]}")

            r,g,b = colorsys.hsv_to_rgb(h, s, v)

            print(f"original RGB: {colors}")
            print(f"altered RGB: {[r,g,b]}")

            for bulb in bulbs:
                await bulb["light"].turn_on(PilotBuilder(
                    speed=200,
                    rgb=(r*255,g*255,b*255),
                    brightness=(v*255)
                ))

if __name__ == "__main__":
    asyncio.run(main())
