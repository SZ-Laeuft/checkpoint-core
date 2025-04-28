import time
import json
import websockets
from mfrc522 import SimpleMFRC522
import asyncio
import requests
import urllib3
urllib3.disable_warnings()

async def send_to_websocket(websocket, data):

    # Send the data as a JSON string
    await websocket.send(json.dumps(data))
    print(f"Sent data: {data} to WebSocket at {time.asctime()}")

async def main():
    reader = SimpleMFRC522()

    lastid = 0
    read_recently = False
    failed = False

    # Establish WebSocket connection once
    uri = "ws://localhost:8080"

    async with websockets.connect(uri) as websocket:
        while True:
            if not read_recently:
                print("\nReady to scan!")
                read_recently = True
                await send_to_websocket(websocket, {"state": "idle", "uid": "-1", "repsone": "-1", "extras":""})

            uid = reader._read_id()
            if lastid != uid or failed:
                lastid = uid

                print(f'Read UID: {uid} at {time.asctime()}')
                await send_to_websocket(websocket, {"state": "loading", "uid": uid, "repsone": "-1", "extras":""})

                url = f'https://192.168.68.68:44320/api/CompleteRound'
                headers = {'Content-Type': 'application/json'}
                data = {
                    "uid": uid
                }
                try:
                    response = requests.post(url, headers=headers, json=data, verify=False)
                    if response.status_code == 500:
                        print('UID doesnt exist!')
                        await send_to_websocket(websocket, {"state": "error", "uid": uid, "repsone": "500",
                                                            "extras":"Hoppala!|Fehler:|UID existiert nicht!"})
                    elif response.status_code == 200:
                        print('Round logged for UID ' + str(uid) + " at " + str(time.asctime()))
                        await send_to_websocket(websocket, {"state": "success", "uid": uid, "repsone": "200",
                                                            "extras": ""})
                    else:
                        await send_to_websocket(websocket, {"state": "error", "uid": uid, "repsone": response.status_code,
                                                            "extras": ""})
                        raise RuntimeWarning("Unexpected response from server; code:" + response.status_code)

                except Exception as e:
                    print("Exception:", str(e))
                    failed = True

                read_recently = False
            await asyncio.sleep(1)  # Add a small delay to avoid high CPU usage

if __name__ == '__main__':
    asyncio.run(main())
