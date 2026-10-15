# Remote access with a Google login

The studio has no user accounts of its own: if you publish it unprotected, anyone can generate audio with your server. Put **oauth2-proxy** in front of it.

1. Create an OAuth client in Google Cloud (type *Web*) with the redirect URI `https://voice.your-domain.com/oauth2/callback`.
2. Create `oauth.env` (permissions `600`, **never commit it**):
   ```
   OAUTH2_PROXY_CLIENT_ID=YOUR_CLIENT_ID_HERE
   OAUTH2_PROXY_CLIENT_SECRET=YOUR_CLIENT_SECRET_HERE
   # Fill it with the output of:  openssl rand -base64 32 | head -c 32
   OAUTH2_PROXY_COOKIE_SECRET=
   OAUTH2_PROXY_REDIRECT_URL=https://voice.your-domain.com/oauth2/callback
   ```
3. Create `allowed-emails.txt` with the emails allowed in (one per line).
4. Add this service to `docker-compose.yml` and **remove the `ports` from `voz-studio`**:
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
5. In your HTTPS proxy (Nginx Proxy Manager, Caddy…), point `voice.your-domain.com` to `voz-auth:4180`.
