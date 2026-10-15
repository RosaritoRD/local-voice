# 💸 Ahorro y mejoras

## Gastar menos

1. **Voz sin coste por carácter.** Los servicios de voz en la nube cobran por cada carácter. Aquí el coste de cada audio es 0: solo pagas el servidor, que ya tienes.
2. **Usa Piper para borradores y Kokoro para la versión final.** Piper es unas 2 veces más rápido; para revisar un guion no hace falta la mejor voz.
3. **`OMP_NUM_THREADS` igual a tus CPUs.** Con más hilos que núcleos el audio sale más lento, no más rápido.
4. **Combínalo con la nube.** Puedes usar voz local para los vídeos largos o para pruebas, y una voz de pago solo donde más se nota, por ejemplo en los primeros segundos de un Short.
5. **Sin salida a internet.** El contenedor no necesita red: menos superficie de ataque y nada que pague tráfico.

## Hacerlo mejor

1. **Velocidad 0,88–0,92** para oraciones y meditaciones. Más rápido suena a anuncio.
2. **Escribe para el oído:** frases cortas y un párrafo por idea. El motor mete una pausa entre párrafos.
3. **Compara antes de cambiar.** Si sustituyes una voz de pago por una local en un canal, mide la retención durante una semana antes de decidir: una voz más plana puede costar vistas.
4. **Ideas para ampliarlo:** clonación de voz con un motor que lo permita, cola de trabajos para textos muy largos, o un `TTS_PROVIDER=local` en tu app de vídeo.
