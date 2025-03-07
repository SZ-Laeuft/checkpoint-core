from time import sleep
from mfrc522 import SimpleMFRC522
import time
import requests
import urllib3
urllib3.disable_warnings()

def main():
    reader = SimpleMFRC522()

    lastid = 0
    read_recently = False
    failed = False

    while True:
        if not read_recently:
            print("\nReady to scan!")
            read_recently = True

        tag_id = reader._read_id()
        if lastid!=tag_id or failed:
            lastid=tag_id

            print(f'Read UID: {tag_id} at {time.asctime()}')

            url = f'https://192.168.68.68:44320/api/CompleteRound'
            headers = {'Content-Type': 'application/json'}
            data = {
                "uid": tag_id
            }

            try:
                response = requests.post(url, headers=headers, json=data, verify=False)
                print(response.json())
                print(response.status_code)
            except Exception as e:
                print("Exception:", str(e))
                failed = True

            read_recently = False

if __name__ == '__main__':
    main()
