# AegisBot

Bot de moderación para Discord escrito en Python con discord.py 2.x. Usa slash commands únicamente.

Bilingüe (español e inglés), todo configurable desde el servidor sin tocar código.

---

## Funciones principales

**Moderación**
- Kick, ban con confirmación, unban, mute/unmute automático con rol
- Limpiar hasta 500 mensajes en bulk
- Lock/unlock de canales

**AutoMod**
- Filtro de palabras con soporte de acentos (unidecode)
- Anti-links, anti-invites independientes
- Filtro de mayúsculas y spam de emojis
- Anti-spam con expulsión automática
- Anti-raid con lockdown completo del servidor
- Alerta cuando entra una cuenta nueva (configurable por días de antigüedad)

**Tickets**
- Panel público con botón para abrir ticket
- Canal privado por usuario con permisos automáticos
- Transcript del ticket al cerrarlo
- Canal de logs de apertura y cierre

**Giveaways**
- Tablero en vivo que se actualiza cada 15 minutos
- Filtro por plataforma (Steam, Epic, PS4, Xbox, Switch, etc.)

**Reportes globales**
- Marca usuarios entre servidores
- Alerta automática cuando el usuario reportado entra a cualquier servidor con el bot

**Utilidades**
- `/clima` — clima en tiempo real vía wttr.in
- `/embed` — anuncia con embed personalizado
- `/info`, `/usuario` — info del servidor y del miembro
- Tarjeta de bienvenida con imagen generada con Pillow
- Status dinámico que rota cada 30 segundos

---

## Configuración

Todo se maneja desde `/config`. Desde ahí puedes:

- Agregar o quitar roles de moderador
- Definir el canal de logs y el de bienvenida
- Configurar el anti-spam (mensajes por ventana de tiempo)
- Activar o desactivar anti-links, anti-invites, caps filter, emoji filter, anti-raid
- Cambiar el idioma del bot (español o inglés)
- Gestionar el filtro de palabras

Para el sistema de tickets hay un panel aparte en `/tickets`.

---

## Instalación

**Requisitos**
- Python 3.10 o superior
- discord.py 2.x
- aiohttp

**Opcionales** (mejoran funciones pero no son obligatorias)
- Pillow — tarjeta de bienvenida con imagen
- unidecode — filtro de palabras más robusto contra evasión con acentos
- emoji — conteo preciso de emojis Unicode

```bash
pip install discord.py aiohttp
pip install pillow unidecode emoji  # opcionales
```

**Setup**

1. Clona el repositorio
2. Copia `config.py` desde `config.example.py` y pon tu token
3. Ejecuta `python orion.py`

En el primer arranque el bot sincroniza los slash commands globalmente. Si los comandos no aparecen en tu servidor, usa `/sync`.

---

## Permisos necesarios

El bot necesita estos permisos para funcionar correctamente:

- Manage Channels
- Manage Roles
- Kick Members
- Ban Members
- Manage Messages
- Send Messages
- Embed Links
- Read Message History
- View Channels

---

## Archivos de datos

El bot guarda la configuración de cada servidor en `server_config.json`. Los logs de mensajes eliminados y editados se escriben en `message_logs/<guild_id>.txt`.

Ninguno de los dos se sube al repositorio (están en `.gitignore`).

---

## Estructura

```
orion.py          — código principal
config.py         — token (no subir)
config.example.py — plantilla sin datos sensibles
server_config.json — generado automáticamente
message_logs/      — generado automáticamente
```

---

## Notas

- Desarrollado y probado en Pydroid 3 (Android) con Python 3.13
- Sin base de datos externa, todo en JSON local
- Sin comandos de prefijo, solo slash commands

---

*by Anthonydev*
