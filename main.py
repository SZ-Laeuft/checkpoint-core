import time
import json
from mfrc522 import SimpleMFRC522
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

def send_to_server(data):
    try:
        response = requests.post("http://localhost:8080/nfc", json=data, verify=False)
        print(f"Sent data: {data} | Response: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Failed to send data: {data} | Error: {e}")

def main():
    reader = SimpleMFRC522()
    lastid = None
    read_recently = False
    failed = False

    while True:
        try:
            if not read_recently:
                print("\nReady to scan!")
                read_recently = True
                send_to_server({
                    "state": "idle", "uid": "-1", "response": "-1", "extras": ""
                })

            raw_uid = reader._read_id()

            if raw_uid is None or not str(raw_uid).isdigit():
                print("Invalid UID read. Skipping.")
                time.sleep(1)
                continue

            uid = raw_uid

            if lastid != uid or failed:
                lastid = uid
                print(f"Read UID: {uid} at {time.asctime()}")
                send_to_server({
                    "state": "loading", "uid": uid, "response": "-1", "extras": ""
                })

                url = 'http://192.168.68.68:8080/api/Lap/CompleteRound'
                headers = {"Content-Type": "application/json"}
                data = {"uid": uid}

                try:
                    response = requests.post(url, headers=headers, json=data, verify=False)
                    print("POST Response:", response.status_code, response.text)

                    if response.status_code == 500:
                        print("UID doesn't exist!")
                        send_to_server({
                            "state": "error", "uid": uid, "response": "500",
                            "extras": "Hoppala!|Fehler:|UID existiert nicht!"
                        })

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

                                send_to_server({
                                    "state": "success", "uid": uid, "response": "200", "extras": extratext
                                })

                            else:
                                send_to_server({
                                    "state": "error", "uid": uid,
                                    "response": str(response_ciu.status_code),
                                    "extras": "Hoppala!|Fehler:|Nutzerdaten fehler!"
                                })
                        except Exception as e:
                            print(f"Exception during CIU request: {e}")
                            send_to_server({
                                "state": "error", "uid": uid, "response": "-1",
                                "extras": f"Hoppala!|Fehler:|{e}"
                            })

                    else:
                        send_to_server({
                            "state": "error", "uid": uid, "response": str(response.status_code),
                            "extras": "Unerwarteter Serverstatus"
                        })
                        raise RuntimeWarning(f"Unexpected response from server: {response.status_code}")

                    failed = False

                except Exception as e:
                    print(f"Exception during POST request: {e}")
                    send_to_server({
                        "state": "error", "uid": uid, "response": "-1",
                        "extras": f"Hoppala!|Fehler:|{e}"
                    })
                    failed = True

                read_recently = False

            time.sleep(3)

        except Exception as e:
            print(f"Main loop exception: {e}. Retrying in 0.5s...")
            time.sleep(0.5)

if __name__ == '__main__':
    main()
