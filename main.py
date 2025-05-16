import time
import json
import websockets
from mfrc522 import SimpleMFRC522
import asyncio
import requests
import urllib3
import logging
import os
import sys

# Setup logging to ~/log.txt
log_file_path = os.path.expanduser('~/log.txt')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler(sys.stdout)
    ]
)

# Redirect print to logging
print = lambda *args, **kwargs: logging.info(' '.join(str(arg) for arg in args))


urllib3.disable_warnings()

async def send_to_websocket(websocket, data):
    await websocket.send(json.dumps(data))
    print(f"Sent data: {data} to WebSocket at {time.asctime()}")

async def keep_websocket_alive(websocket):
    while True:
        try:
            pong_waiter = await websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=10)
            print(f"Ping sent at {time.asctime()}")
        except Exception as e:
            print(f"Ping failed: {e}")
            break
        await asyncio.sleep(30)

async def connect_and_run():
    reader = SimpleMFRC522()
    lastid = None
    read_recently = False
    failed = False
    uri = "ws://localhost:8080"

    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as websocket:
                asyncio.create_task(keep_websocket_alive(websocket))

                while True:
                    if not read_recently:
                        print("\nReady to scan!")
                        read_recently = True
                        await send_to_websocket(websocket, {
                            "state": "idle", "uid": "-1", "repsone": "-1", "extras": ""})

                    raw_uid = reader._read_id()

                    # Validate UID
                    if raw_uid is None or not str(raw_uid).isdigit():
                        print("Invalid UID read. Skipping.")
                        await asyncio.sleep(1)
                        continue

                    
                    print (f"Raw UID: {raw_uid}")
                    uid = str(raw_uid)
                    print (f"UID: {uid}")
                    # Convert int to bytes, then to decimal string (big-endian)
                    uid_bytes = raw_uid.to_bytes((raw_uid.bit_length() + 7) // 8, 'big')
                    uid_decimal = ''.join(str(b) for b in uid_bytes)
                    print("Big-endian:", uid_decimal)

                    # Try little-endian if not matching
                    uid_bytes_le = raw_uid.to_bytes((raw_uid.bit_length() + 7) // 8, 'little')
                    uid_decimal_le = ''.join(str(b) for b in uid_bytes_le)
                    print("Little-endian:", uid_decimal_le)

                    if lastid != uid or failed:
                        lastid = uid
                        print(f"Read UID: {uid} at {time.asctime()}")
                        await send_to_websocket(websocket, {
                            "state": "loading", "uid": uid, "repsone": "-1", "extras": ""})

                        url = 'http://192.168.68.68:8080/api/Lap/CompleteRound'
                        headers = {"Content-Type": "application/json"}
                        data = {"uid": uid}

                        try:
                            response = requests.post(url, headers=headers, json=data, verify=False)
                            print("POST Response:", response.status_code, response.text)

                            if response.status_code == 500:
                                print("UID doesn't exist!")
                                await send_to_websocket(websocket, {
                                    "state": "error", "uid": uid, "repsone": "500",
                                    "extras": "Hoppala!|Fehler:|UID existiert nicht!"})

                            elif response.status_code == 200:
                                print(f"Round logged for UID {uid} at {time.asctime()}")
                                get_user_url = f"http://192.168.68.68:8080/api/Checkpoint/ci-by-uid?uid={uid}"

                                try:
                                    response_ciu = requests.get(get_user_url, headers=headers, verify=False)
                                    print("CIU Response:", response_ciu.status_code, response_ciu.text)

                                    if response_ciu.status_code == 200:
                                        user_data = response_ciu.json()
                                        extratext = (
                                            f"{user_data.get('firstName', '')} {user_data.get('lastName', '')}|"
                                            f"Runde:|{user_data.get('roundCount', '')}|"
                                            f"Zeit:|{user_data.get('lapTime', '')}|"
                                            f"Bestzeit:|{user_data.get('fastestLap', '')}"
                                        )

                                        await send_to_websocket(websocket, {
                                            "state": "success", "uid": uid, "repsone": "200", "extras": extratext})

                                    else:
                                        await send_to_websocket(websocket, {
                                            "state": "error", "uid": uid,
                                            "repsone": str(response_ciu.status_code),
                                            "extras": "Hoppala!|Fehler:|Nutzerdaten fehler!"})
                                except Exception as e:
                                    print(f"Exception during CIU request: {e}")
                                    await send_to_websocket(websocket, {
                                        "state": "error", "uid": uid, "repsone": "-1",
                                        "extras": f"Hoppala!|Fehler:|{e}"})

                            else:
                                await send_to_websocket(websocket, {
                                    "state": "error", "uid": uid, "repsone": str(response.status_code),
                                    "extras": "Unerwarteter Serverstatus"})
                                raise RuntimeWarning(f"Unexpected response from server: {response.status_code}")

                            failed = False

                        except Exception as e:
                            print(f"Exception during POST request: {e}")
                            await send_to_websocket(websocket, {
                                "state": "error", "uid": uid, "repsone": "-1",
                                "extras": f"Hoppala!|Fehler:|{e}"})
                            failed = True

                        read_recently = False

                    await asyncio.sleep(3)

        except Exception as e:
            print(f"WebSocket connection failed: {e}. Retrying in 0.5s...")
            await asyncio.sleep(0.5)

if __name__ == '__main__':
    asyncio.run(connect_and_run())
