# ESP32-CAM flashing guide (via Arduino UNO)

This guide provides step-by-step instructions for flashing an **ESP32-CAM** module using an **Arduino UNO** as a passive USB-to-Serial adapter.
The starting point of the guide is the following tutorial: [Programming The ESP32 Cam Using Arduino UNO](https://www.youtube.com/watch?v=7-3piBHV1W0).

## Arduino IDE configuration

Before flashing, ensure your IDE is configured with these specific settings:

1.  **Install Board Manager:** Ensure the ESP32 board index is added in `File > Preferences` and that the ESP32 package is installed via `Tools > Board > Boards Manager`.
2.  **Select Board:** Go to `Tools > Board > ESP32 Arduino` and select **ESP32 Wrover Module**.
3.  **Upload Speed:** Set `Tools > Upload Speed` to **115200**.
4.  **Flash Frequency:** Set `Tools > Flash Frequency` to **40MHz**.
5.  **Partition Scheme:** Set `Tools > Partition Scheme` to **Huge APP (3MB No OTA/1MB SPIFFS)**.
6.  **Select Port:** Select the COM port corresponding to your Arduino UNO.


## Hardware setup

Connect the pins as follows:

| Arduino UNO | ESP32-CAM |
| :--- | :--- |
| **5V** | **5V** |
| **GND** | **GND** |
| **Pin 0 (RX)** | **U0R** |
| **Pin 1 (TX)** | **U0T** |

<img width="2533" height="1505" alt="image" src="https://github.com/user-attachments/assets/b20a1997-e73b-4c7a-9cb0-3b33125edf30" />

---

## Flashing instructions

Follow these steps to upload your firmware:

1.  **Enter Flash Mode:** Connect the `IO0` pin on the ESP32-CAM to a `GND` pin. Keep this connection in place.
2.  **Start Upload:** In the Arduino IDE, set the **Upload Speed** to **115200 baud** and click the **Upload** button.
3.  **Trigger Connection:** Watch the terminal window at the bottom of the IDE. As soon as the `Connecting.......` message appears, press the physical **RST** button on the back of the ESP32-CAM once.
4.  **Wait for Completion:** Allow the upload process to finish. The process is complete when the IDE prints `Leaving...` and `Done uploading`.
5.  **Exit Flash Mode:** Disconnect the jumper wire between `IO0` and `GND`.
6.  **Boot the Board:** Press the **RST** button on the ESP32-CAM again to reboot the board into standard execution mode.
7.  **Verify via Serial Monitor:** Open the Arduino IDE Serial Monitor, set the baud rate to **115200**, and press the `RST` button. You should see the board booting, connecting to Wi-Fi.

---
