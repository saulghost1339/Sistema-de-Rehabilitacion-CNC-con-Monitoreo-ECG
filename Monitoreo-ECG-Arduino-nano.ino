// --- CONFIGURACIÓN DE PINES ---

const int PIN_SENSOR_1 = A0;

const int PIN_SENSOR_2 = A1;



// --- CONFIGURACIÓN DEL FILTRO ---

float alpha = 0.2; // Suavizado

float filtered1 = 0;

float filtered2 = 0;



// Variables para guardar el "Cero" (silencio) de cada sensor

int baseline1 = 0;

int baseline2 = 0;



void setup() {

  Serial.begin(115200);

 

  // --- AUTO-CALIBRACIÓN (TRUCO PRO) ---

  // Leemos el promedio de los primeros 100 valores para saber

  // dónde está la línea plana de tus sensores.

  // ¡IMPORTANTE!: No muevas los músculos durante los primeros 2 segundos al encender.

  long suma1 = 0;

  long suma2 = 0;

  for(int i=0; i<100; i++) {

    suma1 += analogRead(PIN_SENSOR_1);

    suma2 += analogRead(PIN_SENSOR_2);

    delay(10);

  }

  baseline1 = suma1 / 100;

  baseline2 = suma2 / 100;

 

  // Inicializamos filtros con la base detectada

  filtered1 = baseline1;

  filtered2 = baseline2;

}



void loop() {

  // 1. LECTURA "ANTI-GHOSTING" (Optimizada)

  // Bajamos de 10000 a 7500 microsegundos. Es mucho más rápido y funciona igual.

  analogRead(PIN_SENSOR_1);

  delayMicroseconds(7500);    

  int raw1 = analogRead(PIN_SENSOR_1);



  analogRead(PIN_SENSOR_2);

  delayMicroseconds(7500);

  int raw2 = analogRead(PIN_SENSOR_2);



  // 2. FILTRO DIGITAL (EMA)

  filtered1 = (raw1 * alpha) + (filtered1 * (1.0 - alpha));

  filtered2 = (raw2 * alpha) + (filtered2 * (1.0 - alpha));



  // 3. RECTIFICACIÓN (SOLUCIÓN A LA OLA HACIA ABAJO)

  // Calculamos la distancia desde la linea base (valor absoluto)

  // Ahora da igual si el cable está al revés, la gráfica siempre sube.

  int signal1 = abs((int)filtered1 - baseline1);

  int signal2 = abs((int)filtered2 - baseline2);



  // 4. PREPARACIÓN VISUAL

  // Sensor 1 se queda abajo.

  // Sensor 2 lo subimos 500 puntos para que no se encime con el 1.

  int plot1 = signal1;

  int plot2 = signal2 + 0;



  // 5. ENVÍO SERIAL

  Serial.print("Musculo_1:");

  Serial.print(plot1);

  Serial.print(",");

  Serial.print("Musculo_2:");

  Serial.println(plot2);



  delay(5);

  }
