import time
import json
import websockets
from mfrc522 import SimpleMFRC522
import asyncio
import requests
import urllib3

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
        await asyncio.sleep(30)  # Ping every 30 seconds

async def connect_and_run():
    reader = SimpleMFRC522()
    lastid = 0
    read_recently = False
    failed = False
    uri = "ws://localhost:8080"

    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as websocket:
                # Start ping keepalive in the background
                asyncio.create_task(keep_websocket_alive(websocket))

                while True:
                    if not read_recently:
                        print("\nReady to scan!")
                        read_recently = True
                        await send_to_websocket(websocket, {
                            "state": "idle", "uid": "-1", "repsone": "-1", "extras": ""})

                    uid = reader._read_id()
                    if lastid != uid or failed:
                        lastid = uid
                        print(f'Read UID: {uid} at {time.asctime()}')
                        await send_to_websocket(websocket, {
                            "state": "loading", "uid": uid, "repsone": "-1", "extras": ""})

                        url = f'http://192.168.68.68:8080/api/Lap/CompleteRound'
                        headers = {"Content-Type": "application/json"}
                        data = {"uid": str(uid)}
                        try:
                            response = requests.post(url, headers=headers, json=data, verify=False)
                            if response.status_code == 500:
                                print('UID doesnt exist!')
                                await send_to_websocket(websocket, {
                                    "state": "error", "uid": uid, "repsone": "500",
                                    "extras": "Hoppala!|Fehler:|UID existiert nicht!"})
                            elif response.status_code == 200:
                                print('Round logged for UID ' + str(uid) + " at " + str(time.asctime()))
                                get_user_url = f'http://192.168.68.68:8080/api/Checkpoint/ci-by-uid?uid={uid}'
                                response_ciu = requests.get(get_user_url, headers=headers, verify=False)
                                if response_ciu.status_code == 200:
                                    extratext= (response_ciu.json().get('firstName') + " "
                                                + response_ciu.json().get('lastName') + "|"
                                                + "Runde:" + "|" + response_ciu.json().get('roundCount') + "|"
                                                + "Zeit:" + "|" + response_ciu.json().get('lapTime') + "|"
                                                + "Bestzeit:" + "|" + response_ciu.json().get('bestzeit'))

                                    await send_to_websocket(websocket, {
                                        "state": "success", "uid": uid, "repsone": "200", "extras": extratext})

                                else:
                                    await send_to_websocket(websocket, {
                                        "state": "error", "uid": uid, "repsone": response_ciu.status_code,
                                        "extras": "Hoppala!|Fehler:|Nutzerdaten fehler!"})
                            else:
                                await send_to_websocket(websocket, {
                                    "state": "error", "uid": uid, "repsone": response.status_code, "extras": ""})
                                raise RuntimeWarning(
                                    "Unexpected response from server; code:" + str(response.status_code))
                        except Exception as e:
                            print("Exception:", str(e))
                            await send_to_websocket(websocket, {
                                "state": "error", "uid": "-1", "repsone": response.status_code,
                                "extras": ("Hoppala!|Fehler:|" + str(e) )})
                            failed = True

                        read_recently = False

                    await asyncio.sleep(1)

        except Exception as e:
            print(f"WebSocket connection failed: {e}. Retrying in 0.5s...")
            await asyncio.sleep(0.5)

if __name__ == '__main__':
    asyncio.run(connect_and_run())
