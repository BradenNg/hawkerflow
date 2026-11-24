// DHT22 test for ESP32-S3
// Wiring: DHT22 VCC -> 3V3, GND -> GND, DATA -> GPIO 4 (10k pull-up DATA->3V3 if bare 4-pin sensor)
// Libraries: "DHT sensor library" + "Adafruit U
//nified Sensor" (both by Adafruit)

#include <DHT.h>

#define DHT_PIN  4
#define DHT_TYPE DHT22

DHT dht(DHT_PIN, DHT_TYPE);

void setup() {
  Serial.begin(115200);
  delay(1000);  // give the USB serial port time to connect
  Serial.println("DHT22 test starting...");
  dht.begin();
}

void loop() {
  delay(2000);  // DHT22 can only be read about once every 2 seconds

  float humidity = dht.readHumidity();
  float tempC = dht.readTemperature();

  if (isnan(humidity) || isnan(tempC)) {
    Serial.println("FAIL: no reading from DHT22 - check wiring, pin number and pull-up resistor");
    return;
  }

  float heatIndex = dht.computeHeatIndex(tempC, humidity, false);

  Serial.print("OK  Temp: ");
  Serial.print(tempC, 1);
  Serial.print(" C   Humidity: ");
  Serial.print(humidity, 1);
  Serial.print(" %   Feels like: ");
  Serial.print(heatIndex, 1);
  Serial.println(" C");
}
