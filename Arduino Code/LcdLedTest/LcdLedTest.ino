// I2C LCD + traffic-light LED test for ESP32-S3 (HawkerFlow status display)
// Wiring:
//   LCD (I2C backpack) GND -> GND, VCC -> 5V, SDA -> GPIO 8, SCL -> GPIO 9
//   Traffic light module: GND -> GND, R -> GPIO 16, Y -> GPIO 38, G -> GPIO 39
// Library: "LiquidCrystal I2C" by Frank de Brabander (Library Manager)
//
// 1) Scans the I2C bus and prints the LCD address (usually 0x27 or 0x3F).
// 2) Writes text on the LCD.  If the screen is blank/blocks, turn the blue
//    contrast potentiometer on the back of the LCD.
// 3) Cycles red -> yellow -> green.

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

#define SDA_PIN 8
#define SCL_PIN 9
#define LED_R 16
#define LED_Y 38
#define LED_G 39

LiquidCrystal_I2C *lcd = nullptr;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Wire.begin(SDA_PIN, SCL_PIN);

  Serial.println("Scanning I2C bus...");
  uint8_t found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("OK  I2C device at 0x%02X\n", addr);
      if (!found) found = addr;
    }
  }
  if (!found) {
    Serial.println("FAIL: no I2C device - check SDA/SCL/power");
  } else {
    lcd = new LiquidCrystal_I2C(found, 16, 2);
    lcd->init();
    lcd->backlight();
    lcd->setCursor(0, 0);
    lcd->print("HawkerFlow");
    lcd->setCursor(0, 1);
    lcd->printf("LCD at 0x%02X", found);
    Serial.printf("Use LCD_ADDR 0x%02X in HawkerFlow.ino\n", found);
  }

  pinMode(LED_R, OUTPUT);
  pinMode(LED_Y, OUTPUT);
  pinMode(LED_G, OUTPUT);
}

void showLed(int pin, const char *name) {
  digitalWrite(LED_R, pin == LED_R);
  digitalWrite(LED_Y, pin == LED_Y);
  digitalWrite(LED_G, pin == LED_G);
  Serial.printf("LED: %s\n", name);
  if (lcd) {
    lcd->setCursor(0, 1);
    lcd->print("LED:            ");
    lcd->setCursor(5, 1);
    lcd->print(name);
  }
  delay(1000);
}

void loop() {
  showLed(LED_R, "RED");
  showLed(LED_Y, "YELLOW");
  showLed(LED_G, "GREEN");
}
