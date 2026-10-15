# Acceso desde fuera con login de Google

El estudio no tiene usuarios propios: si lo publicas sin protección, cualquiera puede generar audio con tu servidor. Ponle delante **oauth2-proxy**.

1. Crea un cliente OAuth en Google Cloud (tipo *Web*) con la URI de redirección `https://voz.tu-dominio.com/oauth2/callback`.
2. Crea `oauth.env` (permisos `600`, **nunca a git**):
   ```
   OAUTH2_PROXY_CLIENT_ID=AQUI_VA_TU_CLIENT_ID
   OAUTH2_PROXY_CLIENT_SECRET=AQUI_VA_TU_CLIENT_SECRET
   # Rellénalo con el resultado de:  openssl rand -base64 32 | head -c 32
   OAUTH2_PROXY_COOKIE_SECRET=
   OAUTH2_PROXY_REDIRECT_URL=https://voz.tu-dominio.com/oauth2/callback
   ```
3. Crea `allowed-emails.txt` con los correos que pueden entrar (uno por línea).
4. Añade este servicio al `docker-compose.yml` y **quita los `ports` de `voz-studio`**:
   ```yaml
     voz-auth:
       image: quay.io/oauth2-proxy/oauth2-proxy:v7.7.1
       env_file: ./oauth.env
       command:
         - --upstream=http://voz-studio:8090
         - --http-address=0.0.0.0:4180
         - --email-domain=*
         - --authenticated-emails-file=/etc/allowed-emails.txt
         - --provider=google
         - --cookie-secure=true
         - --cookie-expire=8h
         - --skip-provider-button=true
       volumes:
         - ./allowed-emails.txt:/etc/allowed-emails.txt:ro
       ports:
         - "127.0.0.1:4192:4180"
       depends_on: [voz-studio]
   ```
5. En tu proxy con HTTPS (Nginx Proxy Manager, Caddy…), apunta `voz.tu-dominio.com` a `voz-auth:4180`.
