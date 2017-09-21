import time
import RPi.GPIO as gpio

PINS = [7, 11, 12, 13, 15, 16, 18, 22, 29, 31, 32, 33, 36, 37]


def setup_outputs(outputs: list):
    for pin in outputs:
        gpio.setup(pin, gpio.OUT)


def setup():
    gpio.setwarnings(False)
    gpio.setmode(gpio.BOARD)
    setup_outputs(PINS)


def blink(outputs: list):
    for pin in outputs:
        gpio.output(pin, True)
    time.sleep(.2)
    for pin in outputs:
        gpio.output(pin, False)
    time.sleep(.1)


def blink_sequence(outputs: list):
    for pin in outputs:
        gpio.output(pin, True)
        time.sleep(.5)
        gpio.output(pin, False)
        time.sleep(.5)

if __name__ == "__main__":
    setup()
    print("Starting blink forever")
    while True:
        # blink(PINS)
        blink_sequence(PINS)

