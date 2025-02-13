from time import sleep
from mfrc522 import SimpleMFRC522
import time
import requests

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

            url = f'https://192.168.68.116:44320/api/CompleteRound'
            headers = {'Content-Type': 'application/json'}
            data = {
                "uid": tag_id
            }

            try:
                response = requests.post(url, headers=headers, json=data)
                if response.status_code == 200:
                    print(response.json())
                    failed = False
                else:
                    print("\nError sending Data. Retrying...")
                    print(response.json())
                    failed = True
            except Exception as e:
                print("Exception:", str(e))
                failed = True

            read_recently = False

if __name__ == '__main__':
    main()
