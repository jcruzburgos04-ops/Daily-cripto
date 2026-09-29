# Dejar el bot corriendo 24/7 en Oracle Cloud (gratis)

Tiempo total: unos 30–40 minutos. Necesitás una tarjeta (sólo para verificar la identidad) y tu bot de Telegram ya creado con @BotFather (paso 0).

> Oracle cambia su página seguido: si un botón no se llama exactamente igual, buscá el más parecido. Las ideas no cambian.

---

## 0. Crear el bot de Telegram (si todavía no lo hiciste)

1. En Telegram buscá **@BotFather** y mandale `/newbot`.
2. Elegí un nombre (ej. `Alertas Cripto`) y un usuario que termine en `bot` (ej. `mis_alertas_cripto_bot`).
3. Te devuelve un **token** tipo `123456789:AAH...`. Guardalo: lo vas a pegar en el paso 4.
4. Abrí tu bot nuevo (el link que te da BotFather) y apretá **Iniciar**.

---

## 1. Crear la cuenta de Oracle Cloud

1. Entrá a **https://signup.cloud.oracle.com**.
2. País: **Argentina**. Completá nombre y mail, y confirmá el mail.
3. **Home Region → elegí `Brazil East (Sao Paulo)` o `Chile Central (Santiago)`.**
   ⚠️ Esto **no se puede cambiar después** y los servidores gratis sólo se crean en esa región. No elijas una de Estados Unidos: los exchanges bloquean esos servidores.
4. Tarjeta: Oracle hace un cobro de prueba de ~1 USD que después devuelve. Suelen rechazar tarjetas prepagas o virtuales; usá una de débito o crédito común.
5. Esperá el mail de "tu cuenta está lista" (a veces tarda unos minutos, a veces horas).

### Evitar que Oracle te apague la máquina (recomendado)
Oracle puede reclamar las máquinas gratis que ve "ociosas", y este bot consume muy poco. Para evitarlo:

1. Menú ☰ → **Billing & Cost Management** → **Upgrade and Manage Payment** → **Upgrade to Pay As You Go**.
   Seguís sin pagar nada mientras uses sólo recursos "Always Free" (lo que vamos a crear).
2. Para estar tranquilo: ☰ → **Billing & Cost Management** → **Budgets** → **Create Budget** con monto **1 USD** y una alerta a tu mail. Si alguna vez se generara un cobro, te enterás enseguida.

---

## 2. Crear el servidor

1. En la página de inicio de Oracle Cloud: **Create a VM instance** (o ☰ → **Compute** → **Instances** → **Create instance**).
2. **Name**: `bot-cripto`.
3. **Image and shape** → **Edit**:
   - **Image**: **Change image** → **Ubuntu** → la versión más nueva (ej. *Canonical Ubuntu 24.04*). Si hay opción "Minimal", no la uses.
   - **Shape**: **Change shape** → **Ampere** → `VM.Standard.A1.Flex` con **1 OCPU y 6 GB** de memoria. Tiene que decir **"Always Free-eligible"**.
     - Si al crear te dice **"Out of capacity"**: probá de nuevo más tarde o, si no, elegí **Specialty and previous generation** → `VM.Standard.E2.1.Micro` (también es "Always Free", más chiquita, alcanza igual).
4. **Networking**: dejalo como viene (crea la red y le da una **IP pública**). Verificá que **"Assign a public IPv4 address"** esté en **Yes**.
5. **Add SSH keys** → **Generate a key pair for me** → **Save private key**.
   ⚠️ **Guardá ese archivo** (se llama algo como `ssh-key-2026-09-29.key`). Es la llave para entrar al servidor; si la perdés, no podés entrar. No se la pases a nadie.
6. **Create**. En 1–2 minutos el estado pasa a **Running** (verde).
7. Copiá la **Public IP address** que aparece en la página de la instancia (ej. `144.22.33.44`).

No hace falta abrir ningún puerto: el bot sólo sale a internet, no recibe conexiones.

---

## 3. Entrar al servidor

### Windows 10 / 11
1. Mové el archivo de la llave a una carpeta fácil, por ejemplo `C:\Users\TU_USUARIO\oracle\bot.key`.
2. Abrí **PowerShell** y hacé que la llave sea sólo tuya (si no, Windows no te deja usarla):
   ```powershell
   icacls "$HOME\oracle\bot.key" /inheritance:r /grant:r "$($env:USERNAME):R"
   ```
3. Entrá (cambiá la IP por la tuya):
   ```powershell
   ssh -i "$HOME\oracle\bot.key" ubuntu@144.22.33.44
   ```
4. La primera vez pregunta *"Are you sure you want to continue connecting?"* → escribí `yes`.

### Mac / Linux
```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@144.22.33.44
```

Cuando veas algo como `ubuntu@bot-cripto:~$`, estás adentro del servidor.

---

## 4. Instalar el bot (un solo comando)

Adentro del servidor, pegá esto:

```bash
curl -fsSL https://raw.githubusercontent.com/jcruzburgos04-ops/Daily-cripto/main/deploy/setup.sh | bash
```

> Mientras el código esté sólo en la rama `claude/stoic-cannon-w7ypjw` (antes de pasarlo a `main`), usá esta versión:
> ```bash
> curl -fsSL https://raw.githubusercontent.com/jcruzburgos04-ops/Daily-cripto/claude/stoic-cannon-w7ypjw/deploy/setup.sh | BRANCH=claude/stoic-cannon-w7ypjw bash
> ```

El script hace todo solo:
1. Activa las actualizaciones de seguridad automáticas.
2. Instala Docker.
3. Descarga el bot y lo prepara (la primera vez tarda unos minutos).
4. **Te pide el token** de @BotFather → pegalo (clic derecho pega en PowerShell) y Enter.
5. Te pide que le **mandes un mensaje a tu bot** en Telegram → mandale "hola" y apretá Enter. Así detecta tu chat solo.
6. Te manda un **mensaje de prueba** a Telegram.
7. Arranca el bot. Te llega el mensaje **"✅ Bot de alertas iniciado"** con la lista de lo que vigila y de qué exchange saca cada moneda.

Listo: ya podés cerrar la ventana. El bot sigue corriendo en el servidor, y se levanta solo si se cae o si Oracle reinicia la máquina.

Probá mandarle `/estado` al bot en Telegram.

---

## 5. Mantenimiento

Primero entrá al servidor (paso 3) y a la carpeta del bot:

```bash
cd ~/Daily-cripto
```

| Quiero… | Comando |
|---|---|
| Ver qué está haciendo | `sudo docker compose logs -f --tail 50` (salir con Ctrl+C) |
| Agregar una altcoin o cambiar umbrales | `nano config.yaml` → guardar con Ctrl+O, Enter, salir con Ctrl+X → `sudo docker compose restart` |
| Actualizar el bot a la última versión | volver a correr el comando del paso 4 |
| Apagarlo | `sudo docker compose down` |
| Prenderlo | `sudo docker compose up -d` |

---

## Si algo falla

- **El mensaje de inicio dice que no pudo conectar a un exchange**: revisá que la región sea São Paulo o Santiago (paso 1). Si uno solo falla, el bot usa los otros.
- **"No encontré tu mensaje"** durante la instalación: revisá que el token esté bien copiado, mandale otro mensaje al bot y volvé a correr el comando del paso 4.
- **No llegan alertas**: `sudo docker compose logs --tail 100` y fijate si hay errores. `/ping` en Telegram te dice si está vivo.
- **Perdiste la llave SSH**: desde la página de la instancia en Oracle podés usar **Console connection** o crear una instancia nueva.
