#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import subprocess
import sys
import time
import paho.mqtt.client as mqtt
import os
import json
import re
import hashlib

from config import *

ha_autodiscovery_configs = {}

rtl_433_cmd = "/usr/local/bin/rtl_433"

important_rtl_output_re = re.compile("^(Found|Tuned)")

# Define MQTT event callbacks
def on_connect(client, userdata, flags, rc):
    connect_statuses = {
        0: "Connected",
        1: "incorrect protocol version",
        2: "invalid client ID",
        3: "server unavailable",
        4: "bad username or password",
        5: "not authorised"
    }
    print("MQTT: " + connect_statuses.get(rc, "Unknown error"))

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print("Unexpected disconnection")
    else:
        print("Disconnected")

def on_message(client, obj, msg):
    print(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

def on_publish(client, obj, mid):
    print("Pub: " + str(mid))

def on_subscribe(client, obj, mid, granted_qos):
    print("Subscribed: " + str(mid) + " " + str(granted_qos))

def on_log(client, obj, level, string):
    print(string)

def publish_ha_autodiscovery(client, topic, config):
    """publish config topics for Home Assistant AutoDiscovery"""
    """Do duplication check before, so it doesn't repeat"""    
    m = hashlib.sha256()
    m.update( json.dumps(config, sort_keys=True).encode('utf-8') )

    if topic not in ha_autodiscovery_configs or ha_autodiscovery_configs[topic] != m.digest():
        print(f"Publishing config for Home Assistant AutoDiscovery to {topic}")
        client.publish(topic, payload=json.dumps(config), qos=MQTT_QOS, retain=True)
        
        ha_autodiscovery_configs[topic] = m.digest()


# Setup MQTT connection
client = mqtt.Client()

client.on_connect = on_connect
client.on_subscribe = on_subscribe
client.on_disconnect = on_disconnect

if DEBUG:
    print("Debugging messages enabled")
    client.on_log = on_log
    client.on_message = on_message
    client.on_publish = on_publish

if MQTT_PASS:
    print("Connecting with authentication")
    client.username_pw_set(MQTT_USER, password=MQTT_PASS)
else:
    print("Connecting without authentication")

client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

# Start RTL433 listener
print("Starting RTL433")
rtl433_proc = subprocess.Popen(rtl_433_cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

while True:
    if rtl433_proc.poll() is not None:
        print("RTL433 exited with code " + str(rtl433_proc.poll()))
        sys.exit(rtl433_proc.poll())

    for line in iter(rtl433_proc.stdout.readline, '\n'):
        line = line.rstrip()

        if DEBUG:
            print("RTL: " + line)
        elif important_rtl_output_re.match(line):
            print(line)

        if rtl433_proc.poll() is not None:
            print("RTL433 exited with code " + str(rtl433_proc.poll()))
            sys.exit(rtl433_proc.poll())


        try:
            json_dict = json.loads(line)

            print(line)

            if "model" in json_dict:
                
                if json_dict["model"] == "Hideki-TS04":
                    mqtt_type = "sensor"
                    model = json_dict["model"]
                    sensor_id = json_dict["id"]

                    topic_base = os.path.join(MQTT_TOPIC, mqtt_type, model, str(sensor_id))

                    data_topic = os.path.join(topic_base, "data")

                    for sensor_type in ("temperature", "humidity"):
                        config_topic = os.path.join(f"{topic_base}_{sensor_type}", "config")

                        unit_of_measurement = "°C" if sensor_type == "temperature" else "%"
                        value_name = "temperature_C" if sensor_type == "temperature" else sensor_type

                        config = {
                            "device_class": sensor_type,
                            "name": f"{model}_{sensor_id}_{sensor_type}",
                            "state_topic": data_topic,
                            "unit_of_measurement": unit_of_measurement,
                            "value_template": f"{{{{ value_json.{value_name} }}}}",
                            "unique_id": f"{model}_{sensor_id}_{sensor_type}"
                        }
                    
                        publish_ha_autodiscovery(client, config_topic, config)

                    client.publish(data_topic, payload=line, qos=MQTT_QOS, retain=False)


                elif json_dict["model"] == "SimpliSafe-Sensor":
                    mqtt_type = "binary_sensor"
                    model = json_dict["model"]
                    sensor_id = json_dict["id"]
                    

                    topic_base = os.path.join(MQTT_TOPIC, mqtt_type, model, sensor_id)

                    state_topic = os.path.join(topic_base, "state")
                    config_topic = os.path.join(topic_base, "config")
                    data_topic = os.path.join(topic_base, "data")

                    config = {
                        "name": f"{model}_{sensor_id}",
                        "state_topic": state_topic,
                        "unique_id": sensor_id
                    }

                    if sensor_id.startswith("15"):
                        config["device_class"] = "motion"
                        state = "ON" if json_dict["state"] == 2 else "OFF"
                    elif sensor_id.startswith("19"):
                        config["device_class"] = "door"
                        state = "ON" if json_dict["state"] == 1 else "OFF"

                    publish_ha_autodiscovery(client, config_topic, config)

                    client.publish(state_topic, payload=state, qos=MQTT_QOS, retain=False)
                    client.publish(data_topic, payload=line, qos=MQTT_QOS, retain=False)
        except json.decoder.JSONDecodeError:
            pass