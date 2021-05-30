char s[32];
float foo;
int bar;

char foos[10];

// the setup function runs once when you press reset or power the board
void setup() {
  // initialize digital pin LED_BUILTIN as an output.
  pinMode(LED_BUILTIN, OUTPUT);

  Serial.begin(19200);  // opens serial port, sets data rate to 19,200 bps
  foo = -0.2;
  bar = 0;  
}

// the loop function runs over and over again forever
void loop() {

  while (1) {
  
    foo = foo + 0.01;
    bar = bar + 1;
  
    //snprintf(s, sizeof(s), "x;y;z;%f\n", foo);  

    dtostrf(foo, 5, 2, foos);
    
    if (foo > 0) {
      sprintf(s, "+%sg;%d;s;f", foos, bar);
    } else {
      sprintf(s, "%sg;%d;s;f", foos, bar);
    }

    Serial.println(s);
    
    digitalWrite(LED_BUILTIN, HIGH);   // turn the LED on (HIGH is the voltage level)
    delay(200);                       // wait for a second
    digitalWrite(LED_BUILTIN, LOW);    // turn the LED off by making the voltage LOW
    delay(100);                       // wait for a second
  }
}
