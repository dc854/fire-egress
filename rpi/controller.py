"""
Authors: Andrew Mackin (ajm536), David Chen (dc854), Hannah Goldstein (hlg66)
"""
import os
import time
from db import App
import RPi.GPIO as GPIO
import pygame
from pygame.locals import *
import paho.mqtt.client as mqtt

pygame.init()
pygame.display.init()

size = width, height = 320, 240

WHITE = 255, 255, 255
# list GPIO pins for the lights
PIN_LIST = [13, 6, 5, 11, 20, 21, 16, 4, 3,
            2, 17, 27, 9, 10, 22, 25, 19, 26, 12]
my_font = pygame.font.Font(None, 15)
screen = pygame.display.set_mode(size)

left_history = []
right_history = []

# for neo4j
uri = os.environ.get('NEO4J_URI')
user = os.environ.get('NEO4J_USERNAME')
password = os.environ.get('NEO4J_PASSWORD')
app = App(uri, user, password)
app.init_db()

# sensor to number mapping for neo4j
SENSORS = {'sensor1': 6, 'sensor2': 7, 'sensor3': 5}
HEAT_THRESH = 23
# ip address of RPi, must be changed every time
mqtt_broker_ip = "10.49.242.163"

client = mqtt.Client()


def add_to_history(history, msg):
    if msg not in history:
        if len(history) == 3:
            history.pop(0)
        history.append(msg)

# create neo4j model graph


def init_model():
    GPIO.setmode(GPIO.BCM)
    for pin in PIN_LIST:
        GPIO.setup(pin, GPIO.OUT)
    # init each sign
    nonexit_signs = app.get_sign_ids()
    for id in nonexit_signs:
        path = app.shortest_path(id)
        delta_dir = get_delta_dir(path)
        update_signals(app.set_direction(id, delta_dir)[0]['n'])
    exit_signs = app.get_exit_ids()
    for exit in exit_signs:
        update_signals(exit)


def get_sign_dir(path):
    return path[0]['path'][0]['dir']


def get_delta_dir(path):
    try:
        return path[0]['path'][2]['dir']
    except:
        print(path)
        raise IndexError

# set pin to high


def on(pin):
    if type(pin) == int and pin > 0:
        GPIO.output(pin, GPIO.HIGH)

# set pin to low


def off(pin):
    if type(pin) == int and pin > 0:
        GPIO.output(pin, GPIO.LOW)

# change LEDs based on the node


def update_signals(node):
    dir = node['dir']
    q1 = node['q1']
    q2 = node['q2']
    q3 = node['q3']
    q4 = node['q4']
    if dir == 'up':
        on(q3), on(q4)
        off(q1), off(q2)
    elif dir == 'down':
        on(q1), on(q2)
        off(q3), off(q4)
    elif dir == 'right':
        on(q3), on(q2)
        off(q1), off(q4)
    elif dir == 'left':
        on(q1), on(q4)
        off(q3), off(q2)
    else:
        raise AssertionError("invalid direction")

# connect and subscribe to each sensor


def on_connect(client, userdata, flags, rc):
    init_model()
    print("connected...")
    for t in SENSORS:
        client.subscribe(t)

# performs the query when reaching a certain threshold


def on_message(client, userdata, msg):
    alarm_id = SENSORS[msg.topic]
    print("Topic: ", msg.topic, msg.payload.decode("utf-8"))
    m = msg.payload.decode("utf-8")

    # calculate exits if sensor is above threshold
    if not (m == "" or m == "nan") and float(m) >= HEAT_THRESH:
        print("Triggered: ", msg.topic)
        app.set_fire(alarm_id)
        add_to_history(
            left_history, "Fire detected by sensor " + str(msg.topic[-1]))
        nonexit_signs = app.get_sign_ids()

        # get shortest path for each node
        for id in nonexit_signs:
            path = app.shortest_path(id)
            delta_dir = get_delta_dir(path)
            sign_dir = get_sign_dir(path)
            if sign_dir != delta_dir:
                add_to_history(right_history, "Changing sign # " +
                               str(id) + " " + sign_dir + "->" + delta_dir)
                update_signals(app.set_direction(id, delta_dir)[0]['n'])
        screen.fill((0, 0, 0))
        # display left history
        lefty = 20
        for msg in left_history:
            lefty += 20
            text_surface = my_font.render(msg, True, WHITE)
            rect = text_surface.get_rect(center=(70, lefty))
            screen.blit(text_surface, rect)
        # display right history
        righty = 20
        for msg in right_history:
            righty += 20
            text_surface = my_font.render(msg, True, WHITE)
            rect = text_surface.get_rect(center=(230, righty))
            screen.blit(text_surface, rect)
        pygame.display.flip()


client.on_connect = on_connect
client.on_message = on_message

client.connect(mqtt_broker_ip, 1883)
try:
    client.loop_forever()
    GPIO.cleanup()
    app.close()
    client.disconnect
except KeyboardInterrupt:
    GPIO.cleanup()
    app.close()
