/*
  ESP32-S3 CAM (N16R8) - Camera test, no WiFi needed
  ---------------------------------------------------
  What it does:
    1. Starts the camera and tells you which sensor it found (OV2640 / OV3660 / OV5640).
    2. Takes a test photo every few seconds and prints its size + capture time.
    3. When you type  c  in the Serial Monitor (or run grab_photo.py),
       it sends one JPEG photo over USB so you can save and view it on your PC.

  Arduino IDE settings (Tools menu):
    Board            : ESP32S3 Dev Module
    USB CDC On Boot  : Enabled        (if you plug into the port labelled "USB")
    Flash Size       : 16MB (128Mb)
    PSRAM            : OPI PSRAM      <-- REQUIRED, the camera buffers live here
    Partition Scheme : 16M Flash (3MB APP/9.9MB FATFS)
    Core Debug Level : None           <-- keeps log text out of the photo data
*/

#include "esp_camera.h"

// ---------- Pin map for the common "ESP32-S3 CAM N16R8" / ESP32-S3-EYE layout ----------
#define PWDN_GPIO_NUM   -1
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM   15
#define SIOD_GPIO_NUM    4   // SCCB (I2C) data
#define SIOC_GPIO_NUM    5   // SCCB (I2C) clock
#define Y9_GPIO_NUM     16
#define Y8_GPIO_NUM     17
#define Y7_GPIO_NUM     18
#define Y6_GPIO_NUM     12
#define Y5_GPIO_NUM     10
#define Y4_GPIO_NUM      8
#define Y3_GPIO_NUM      9
#define Y2_GPIO_NUM     11
#define VSYNC_GPIO_NUM   6
#define HREF_GPIO_NUM    7
#define PCLK_GPIO_NUM   13

const unsigned long AUTO_TEST_INTERVAL_MS = 5000;
unsigned long lastAutoTest = 0;
bool cameraOk = false;

const char* sensorName(uint16_t pid) {
  switch (pid) {
    case OV2640_PID: return "OV2640";
    case OV3660_PID: return "OV3660";
    case OV5640_PID: return "OV5640";
    case OV7725_PID: return "OV7725";
    default:         return "Unknown";
  }
}

bool initCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk  = XCLK_GPIO_NUM;
  config.pin_pclk  = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href  = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn  = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode    = CAMERA_GRAB_LATEST;   // always give the newest frame

  if (psramFound()) {
    config.frame_size   = FRAMESIZE_VGA;      // 640x480 - safe starting size
    config.jpeg_quality = 10;                 // 0-63, lower = better quality
    config.fb_count     = 2;
    config.fb_location  = CAMERA_FB_IN_PSRAM;
  } else {
    Serial.println("WARNING: PSRAM not found! Set Tools > PSRAM > OPI PSRAM.");
    config.frame_size   = FRAMESIZE_QVGA;     // 320x240 fallback
    config.jpeg_quality = 12;
    config.fb_count     = 1;
    config.fb_location  = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init FAILED, error 0x%x\n", err);
    Serial.println("Check: ribbon cable seated & latched, contacts facing the right way, PSRAM enabled.");
    return false;
  }

  sensor_t* s = esp_camera_sensor_get();
  Serial.printf("Camera init OK. Sensor: %s (PID 0x%04X)\n", sensorName(s->id.PID), s->id.PID);

  // Some sensors come up upside down / mirrored - flip here if your image looks wrong
  if (s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);
    s->set_brightness(s, 1);
    s->set_saturation(s, -2);
  }
  return true;
}

// Capture one frame and report how it went. Returns true on success.
bool testCapture() {
  unsigned long t0 = millis();
  camera_fb_t* fb = esp_camera_fb_get();
  unsigned long dt = millis() - t0;

  if (!fb) {
    Serial.println("Capture FAILED (no frame buffer).");
    return false;
  }
  Serial.printf("Captured %ux%u JPEG, %u bytes in %lu ms\n",
                fb->width, fb->height, fb->len, dt);
  esp_camera_fb_return(fb);
  return true;
}

// Send one JPEG over Serial, framed so grab_photo.py can find it:
//   JPG_START <length>\n  <raw bytes>  \nJPG_END\n
void sendPhoto() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Capture FAILED (no frame buffer).");
    return;
  }
  Serial.printf("JPG_START %u\n", fb->len);
  Serial.write(fb->buf, fb->len);
  Serial.print("\nJPG_END\n");
  Serial.flush();
  esp_camera_fb_return(fb);
}

void setup() {
  Serial.begin(921600);
  delay(2000);  // give the Serial Monitor time to connect
  Serial.println("\n=== ESP32-S3 CAM test ===");
  Serial.printf("PSRAM: %s, size %u bytes\n", psramFound() ? "found" : "NOT found", ESP.getPsramSize());

  cameraOk = initCamera();
  if (cameraOk) {
    // throw away the first couple of frames so auto-exposure can settle
    for (int i = 0; i < 3; i++) {
      camera_fb_t* fb = esp_camera_fb_get();
      if (fb) esp_camera_fb_return(fb);
    }
    testCapture();
    Serial.println("Type 'c' to send a photo to the PC (use grab_photo.py to save it).");
  }
}

void loop() {
  if (!cameraOk) {
    delay(1000);
    return;
  }

  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == 'c') sendPhoto();
  }

  if (millis() - lastAutoTest > AUTO_TEST_INTERVAL_MS) {
    lastAutoTest = millis();
    testCapture();
  }
}
