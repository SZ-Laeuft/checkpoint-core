import time
import json
import websockets
from mfrc522 import SimpleMFRC522  # Assuming this is the correct import
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
        logging.StreamHandler(sys.stdout)  # Also print to console
    ]
)

# Redirect print to logging for consistent output
# You can comment this out if you prefer direct print for some things
# print_original = print
# print = lambda *args, **kwargs: logging.info(' '.join(map(str, args)))


urllib3.disable_warnings()

# Configuration for the 5-byte UID generation
MFRC522_UID_PREFIX_BYTE = 0x88  # Observed prefix, e.g., 0x88


async def send_to_websocket(websocket, data):
    await websocket.send(json.dumps(data))
    logging.info(f"Sent data: {data} to WebSocket at {time.asctime()}")


async def keep_websocket_alive(websocket):
    while True:
        try:
            pong_waiter = await websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=10)
            logging.info(f"Ping sent at {time.asctime()}")
        except Exception as e:
            logging.error(f"Ping failed: {e}")
            break  # Exit task if ping fails
        await asyncio.sleep(30)


async def connect_and_run():
    reader = SimpleMFRC522()
    last_processed_uid_string = None  # To store the 5-byte UID string
    read_recently = False  # To manage idle state message
    failed_last_attempt = False  # To retry if API call failed
    uri = "ws://localhost:8080"

    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as websocket:
                logging.info(f"Successfully connected to WebSocket: {uri}")
                asyncio.create_task(keep_websocket_alive(websocket))
                read_recently = False  # Reset for new connection

                while True:
                    if not read_recently:
                        logging.info("\nReady to scan!")
                        await send_to_websocket(websocket, {
                            "state": "idle", "uid": "-1", "repsone": "-1", "extras": ""})
                        read_recently = True  # Set true after sending idle

                    raw_uid_int = reader._read_id()  # This returns an integer

                    if raw_uid_int is None:
                        # logging.info("No card detected or read error from _read_id().") # Can be spammy
                        await asyncio.sleep(0.5)  # Short sleep if no card
                        continue

                    # --- New 5-byte UID Generation Logic ---
                    try:
                        # Determine the number of bytes in the integer UID
                        # (raw_uid_int.bit_length() + 7) // 8 gives byte length
                        num_raw_uid_bytes = (raw_uid_int.bit_length() + 7) // 8
                        if num_raw_uid_bytes == 0 and raw_uid_int == 0:  # Handle case where UID is 0
                            num_raw_uid_bytes = 1

                        if num_raw_uid_bytes < 3:
                            logging.warning(f"Raw UID integer {raw_uid_int} (0x{raw_uid_int:X}) is too short "
                                            f"({num_raw_uid_bytes} bytes), needs at least 3 bytes. Skipping.")
                            await asyncio.sleep(1)
                            continue

                        raw_uid_byte_array = raw_uid_int.to_bytes(num_raw_uid_bytes, 'big')

                        m1_prefix = MFRC522_UID_PREFIX_BYTE
                        m2_uid_byte1 = raw_uid_byte_array[0]
                        m3_uid_byte2 = raw_uid_byte_array[1]
                        m4_uid_byte3 = raw_uid_byte_array[2]

                        m5_bcc = m1_prefix ^ m2_uid_byte1 ^ m3_uid_byte2 ^ m4_uid_byte3

                        # This is the new 5-byte (10-hex char) UID string
                        current_uid_string = (
                            f"{m1_prefix:02X}"
                            f"{m2_uid_byte1:02X}"
                            f"{m3_uid_byte2:02X}"
                            f"{m4_uid_byte3:02X}"
                            f"{m5_bcc:02X}"
                        )
                        logging.info(f"Raw integer from _read_id(): {raw_uid_int} (0x{raw_uid_int:X})")
                        logging.info(
                            f"Derived Pyscard UID bytes (M2,M3,M4): {m2_uid_byte1:02X}{m3_uid_byte2:02X}{m4_uid_byte3:02X}")
                        logging.info(f"Calculated 5-byte UID string: {current_uid_string}")

                    except Exception as e_uid_gen:
                        logging.error(f"Error during 5-byte UID generation: {e_uid_gen}. Raw UID int: {raw_uid_int}")
                        await asyncio.sleep(1)
                        continue
                    # --- End of New 5-byte UID Generation Logic ---

                    # Process if new UID or if previous attempt failed
                    if last_processed_uid_string != current_uid_string or failed_last_attempt:
                        last_processed_uid_string = current_uid_string  # Store the new 5-byte UID

                        logging.info(f"Processing UID: {current_uid_string} at {time.asctime()}")
                        await send_to_websocket(websocket, {
                            "state": "loading", "uid": current_uid_string, "repsone": "-1", "extras": ""})

                        url = 'http://192.168.68.68:8080/api/Lap/CompleteRound'
                        headers = {"Content-Type": "application/json"}
                        data_payload = {"uid": current_uid_string}  # Use the new 5-byte UID

                        try:
                            response = requests.post(url, headers=headers, json=data_payload, verify=False, timeout=10)
                            logging.info(
                                f"POST Response for {current_uid_string}: {response.status_code} {response.text}")

                            if response.status_code == 500:
                                logging.warning(f"UID {current_uid_string} doesn't exist on server!")
                                await send_to_websocket(websocket, {
                                    "state": "error", "uid": current_uid_string, "repsone": "500",
                                    "extras": "Hoppala!|Fehler:|UID existiert nicht!"})
                            elif response.status_code == 200:
                                logging.info(f"Round logged for UID {current_uid_string} at {time.asctime()}")
                                get_user_url = f"http://192.168.68.68:8080/api/Checkpoint/ci-by-uid?uid={current_uid_string}"
                                try:
                                    response_ciu = requests.get(get_user_url, headers=headers, verify=False, timeout=10)
                                    logging.info(
                                        f"CIU Response for {current_uid_string}: {response_ciu.status_code} {response_ciu.text}")
                                    if response_ciu.status_code == 200:
                                        user_data = response_ciu.json()
                                        extratext = (
                                            f"{user_data.get('firstName', '')} {user_data.get('lastName', '')}|"
                                            f"Runde:|{user_data.get('roundCount', '')}|"
                                            f"Zeit:|{user_data.get('lapTime', '')}|"
                                            f"Bestzeit:|{user_data.get('fastestLap', '')}"
                                        )
                                        await send_to_websocket(websocket, {
                                            "state": "success", "uid": current_uid_string, "repsone": "200",
                                            "extras": extratext})
                                    else:
                                        await send_to_websocket(websocket, {
                                            "state": "error", "uid": current_uid_string,
                                            "repsone": str(response_ciu.status_code),
                                            "extras": "Hoppala!|Fehler:|Nutzerdaten fehler!"})
                                except Exception as e_ciu:
                                    logging.error(f"Exception during CIU request for {current_uid_string}: {e_ciu}")
                                    await send_to_websocket(websocket, {
                                        "state": "error", "uid": current_uid_string, "repsone": "-1",  # repsone typo?
                                        "extras": f"Hoppala!|Fehler CIU:|{e_ciu}"})  # Shorter error
                            else:
                                logging.error(
                                    f"Unexpected server status for {current_uid_string}: {response.status_code}")
                                await send_to_websocket(websocket, {
                                    "state": "error", "uid": current_uid_string, "repsone": str(response.status_code),
                                    "extras": "Unerwarteter Serverstatus"})

                            failed_last_attempt = False  # Success or handled error

                        except requests.exceptions.RequestException as e_req:  # Catch specific requests errors
                            logging.error(f"RequestException for {current_uid_string}: {e_req}")
                            await send_to_websocket(websocket, {
                                "state": "error", "uid": current_uid_string, "repsone": "-1",
                                "extras": f"Hoppala!|Netzwerkfehler:|{e_req}"})  # Shorter error
                            failed_last_attempt = True
                        except Exception as e_post:  # Catch other errors during POST
                            logging.error(f"Generic Exception during POST for {current_uid_string}: {e_post}")
                            await send_to_websocket(websocket, {
                                "state": "error", "uid": current_uid_string, "repsone": "-1",
                                "extras": f"Hoppala!|Fehler Post:|{e_post}"})  # Shorter error
                            failed_last_attempt = True

                        read_recently = False  # Allow idle message again after processing a card

                    await asyncio.sleep(1)  # Main loop sleep after checking/processing a card

        except websockets.exceptions.ConnectionClosedOK:
            logging.info("WebSocket connection closed normally.")
        except websockets.exceptions.ConnectionClosedError as e_ws_closed_err:
            logging.error(f"WebSocket connection closed with error: {e_ws_closed_err}. Retrying in 5s...")
        except ConnectionRefusedError:
            logging.error(f"WebSocket connection refused at {uri}. Is the server running? Retrying in 5s...")
        except Exception as e_main_loop:
            logging.error(f"Main loop WebSocket connection error: {e_main_loop}. Retrying in 5s...")

        await asyncio.sleep(5)  # Wait before retrying connection


if __name__ == '__main__':
    try:
        asyncio.run(connect_and_run())
    except KeyboardInterrupt:
        logging.info("Program terminated by user (Ctrl+C)")
    finally:
        logging.info("Application shutdown.")
