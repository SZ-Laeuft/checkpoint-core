from time import sleep
from mfrc522 import SimpleMFRC522
import time
import requests

def main():
    reader = SimpleMFRC522()

    lastid = 0
    read_recently = False

    while True:
        if not read_recently:
            print("\nReady to scan!")
            read_recently = True

        tag_id = reader._read_id()
        if lastid!=tag_id:
            lastid=tag_id

            print(f'Read UID: {tag_id} at {time.localtime()}')

            url = f'https://192.168.68.116:44320/api/CompleteRound?id={tag_id}'
            headers = {'Content-Type': 'application/json'}

            try:
                response = requests.get(url, headers=headers, verify=False)
                if response.status_code == 200:
                    print(response.json())
                else:
                    print("\nError sending Data")
            except Exception as e:
                print("Exception:", str(e))

            read_recently = False

if __name__ == '__main__':
    main()
