from time import sleep
from mfrc522 import SimpleMFRC522


def main():
    reader = SimpleMFRC522()
    lastid = 0;
    while True:
        print("Hold a tag near the reader")
        tag_id = reader._read_id()
        if lastid!=tag_id:
            lastid=tag_id
            print(f'ID: {tag_id}')
            sleep(1)

if __name__ == '__main__':
    main()
