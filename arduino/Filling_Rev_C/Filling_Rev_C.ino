
// Arduino Nano Every code for PCS Filling Machine

//  Messages received from RPi host:
//    - String of dispense valve open time in milliseconds terminated with "_"
//    - P_/p_ to turn on/off air pressure (note, also terminated with a "_").
//
//  Messages sent (streamed) to RPi host:
//    - Balance weight, compressor pressure, Stop switch state,
//      and Footswitch state. 
//    - If balance data stops, message replaces balance data
//      with "$".
//    Data Format example:  "+    0.00g  ;194;s;f"
//

#include "millisDelay.h" 


// Digital I/O
int footswitch = 3;  // Footswitch: Switch pressed = low
int stopswitch = 4;  // Stop Switch: Switch pressed = low
int dispensevalveoutput = 2;  // Dispense Valve Output on = high
int airvalveoutput = 5; // Air valve output 
int everypcbled = 13; // For watchdog led

// Analog I/O
int pressurein = A0;  // Pressure transducer
   // 0 psi = 1 volt = 205
   // 30 psi = 5 volts = 1023
 
// Variables
String inString = "";          // string to hold input
String stopswitchstring = "";  // stop switch string S = switch pressed, s = not pressed
String footswitchstring = "";  // foot switch string F = switch pressed, F = not pressed

String pulsetimestring = "";   // dispense valve pulse time string
String pressurevalvestring = "";  // pressure valve string. P = valve on, p = valve off

String incomingString = "";    // Weight string from scale

int scalemaxtime = 1000;

int pulsetime;                 // time in milliseconds to turn the output on
int footswitchstate = 0;       // stores the state of the footswitch;
int stopswitchstate = 0;       // stores the state of the stopswitch;
int pressurevalue = 0;         // stores the pressure transducer value

int previousscaleMillis = 0;
int currentscaleMillis = 0;

bool scaleoffline = true;

unsigned long previousdispenseMillis = 0;
unsigned long currentdispenseMillis = 0;

//-----------------------------------------------------------------------
void setup() {
pinMode(dispensevalveoutput, OUTPUT);
pinMode(footswitch, INPUT);
pinMode(stopswitch, INPUT);
pinMode(airvalveoutput, OUTPUT);
pinMode (everypcbled, OUTPUT);

Serial.begin(19200);  // opens serial port (USB), sets data rate to 19,200 bps
Serial1.begin(19200);  // opens serial port 1 (hardware) , sets data rate to 19,200 bps
// Serial1.setTimeout(1000);

}
//-----------------------------------------------------------------------
void loop() {

// Make the Nano Every pcb led blink at 1 Hz

  if (millis() % 1000 > 500)
  digitalWrite(everypcbled, LOW);  // turn the led off
  else
  digitalWrite(everypcbled, HIGH);  // turn the led oon

// Get the pressure and switch inputs

pressurevalue = analogRead(pressurein);     // read the pressure input pin

footswitchstate = digitalRead(footswitch);  // read the footswitch input pin
  if (footswitchstate == LOW) {
    footswitchstring = "F";
    }
  else {
    footswitchstring = "f";
    }
stopswitchstate = digitalRead(stopswitch);  // read the stopswitch input pin
  if (stopswitchstate == LOW) {
    stopswitchstring = "S";
    pulsetime = 0;                      // turn off the dispense valve
    digitalWrite(airvalveoutput, LOW);  // turn off the air valve
    }
  else {
    stopswitchstring = "s";
    }

// Read the host serial commands

  char inchar;
  
  while (Serial.available() > 0) {
    inchar = Serial.read();
    inString += (char)inchar;
    if (inchar == '_') {
      if (inString == "P_")
        digitalWrite(airvalveoutput, HIGH);  // turn the valve on
      if (inString == "p_")
        digitalWrite(airvalveoutput, LOW);  // turn the valve off
//      Serial.println(inString);  // for testing only
      
      pulsetime = inString.toInt();  // 0 if not digits
//    Serial.println(pulsetime);  // for testing only
      inString = "";  // clear the string for new input:
     }
   } 

// Pulse the dispense valve

currentdispenseMillis = millis();
  if (currentdispenseMillis - previousdispenseMillis >= pulsetime) {
    previousdispenseMillis = currentdispenseMillis;
    digitalWrite(dispensevalveoutput, LOW);   // time to turn the valve off
    pulsetime = 0; }
  else {
    digitalWrite(dispensevalveoutput, HIGH);  // turn the valve on
    }

    
// Send the scale data
// If the scale is off line just send
// the pressure and the switch states
 
  currentscaleMillis = millis();
  if (currentscaleMillis - previousscaleMillis <= scalemaxtime) {
    scaleoffline = false;  }
  else   {
    scaleoffline = true;
  }

  // check if data is available from the scale
  if (Serial1.available() > 0) {
    // read the incoming string:
  incomingString = Serial1.readStringUntil('\n');
  previousscaleMillis = currentscaleMillis;
  }
 
  if (scaleoffline == true) {
    incomingString = "$"; } 
    Serial.print(incomingString);
    Serial.print(";");
    Serial.print(pressurevalue);
    Serial.print(";");
    Serial.print(stopswitchstring);
    Serial.print(";");
    Serial.println(footswitchstring);

 } 
 
