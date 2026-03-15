# Copyright (c) 2026 Anthonydev — Todos los derechos reservados.

import discord
from discord.ext import commands, tasks
from discord import ui, app_commands
import logging
from collections import defaultdict
import time
import json
import os
import re
import asyncio
import aiohttp
import io
from datetime import datetime, timezone
import config

# --- librerías opcionales (instaladas en Pydroid) ---
try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False

try:
    import emoji as emoji_lib
    EMOJI_LIB_OK = True
except ImportError:
    EMOJI_LIB_OK = False

try:
    import unidecode as _unidecode
    def normalizar_texto(texto: str) -> str:
        return _unidecode.unidecode(texto).lower()
    UNIDECODE_OK = True
except ImportError:
    def normalizar_texto(texto: str) -> str:
        return texto.lower()
    UNIDECODE_OK = False

LOGS_DIR = "message_logs"
os.makedirs(LOGS_DIR, exist_ok=True)

# --- config ---

CONFIG = {
    "TOKEN": config.TOKEN,
    "PREFIX": "\x00"  # prefijo nulo — solo usamos slash commands
}

# --- colores ---

COLORS = {
    "kick":       0xF59E0B,
    "ban":        0xEF4444,
    "unban":      0x22C55E,
    "mute":       0x6B7280,
    "unmute":     0x3B82F6,
    "lock":       0xEF4444,
    "unlock":     0x22C55E,
    "spam":       0xDC2626,
    "raid":       0xFF0000,
    "bienvenida": 0x6366F1,
    "adios":      0x94A3B8,
    "panel":      0x5865F2,
    "info":       0x3B82F6,
    "ayuda":      0x8B5CF6,
    "ok":         0x22C55E,
    "ticket":     0x6366F1,
    "ticket_ok":  0x22C55E,
    "ticket_cerrado": 0x94A3B8,
    "clima":      0x38BDF8,
    "meme":       0xF472B6,
    "define":     0xA78BFA,
    "giveaway":   0xF97316,
}

raid_tracker: dict = defaultdict(list)

def make_embed(titulo: str, descripcion: str = None, color: int = COLORS["info"],
               thumbnail: str = None, image: str = None,
               footer: str = "AegisBot • Moderación") -> discord.Embed:
    embed = discord.Embed(title=titulo, description=descripcion, color=color)
    embed.timestamp = discord.utils.utcnow()
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if image:
        embed.set_image(url=image)
    if footer and bot.user:
        embed.set_footer(text=footer, icon_url=bot.user.display_avatar.url)
    return embed

def set_footer(embed: discord.Embed, bot_user: discord.ClientUser,
               seccion: str = "Moderación") -> discord.Embed:
    embed.set_footer(
        text=f"AegisBot • {seccion}",
        icon_url=bot_user.display_avatar.url
    )
    return embed

# ──────────────────────────────────────────────
# HELPERS DE IMAGEN (Pillow)
# ──────────────────────────────────────────────

def cargar_fuente(size: int = 36, negrita: bool = False):
    # whitneysemibold si negrita, ggsans-Medium si no; fallback a Pillow default
    if not PILLOW_OK:
        return None

    # Carpeta donde está orion.py
    base = os.path.dirname(os.path.abspath(__file__))

    rutas = [
        os.path.join(base, "whitneysemibold.otf") if negrita else os.path.join(base, "ggsans-Medium.ttf"),
        os.path.join(base, "whitneymedium.otf"),
        os.path.join(base, "whitneysemibold.otf"),
        os.path.join(base, "ggsans-Medium.ttf"),
    ]
    for ruta in rutas:
        if os.path.exists(ruta):
            try:
                return ImageFont.truetype(ruta, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)   # Pillow 10+
    except TypeError:
        return ImageFont.load_default()            # Pillow < 10


def _construir_tarjeta_sync(avatar_bytes: bytes, nombre: str, servidor: str, numero: int, fecha_cuenta: str) -> bytes:
    avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((130, 130))
    mascara = Image.new("L", (130, 130), 0)
    ImageDraw.Draw(mascara).ellipse((0, 0, 130, 130), fill=255)
    avatar_circ = Image.new("RGBA", (130, 130), (0, 0, 0, 0))
    avatar_circ.paste(avatar_img, (0, 0), mascara)

    tarjeta = Image.new("RGBA", (620, 200), (30, 31, 48))
    draw = ImageDraw.Draw(tarjeta)
    draw.rectangle([(0, 0), (170, 200)], fill=(88, 101, 242))
    draw.rectangle([(0, 192), (620, 200)], fill=(88, 101, 242))
    draw.rectangle([(612, 0), (620, 200)], fill=(88, 101, 242))
    tarjeta.paste(avatar_circ, (20, 35), avatar_circ)

    f_sub     = cargar_fuente(18)
    f_nombre  = cargar_fuente(32, negrita=True)
    f_detalle = cargar_fuente(20)

    draw.text((185, 32),  "Bienvenido/a al servidor!", font=f_sub,     fill=(160, 170, 255))
    draw.text((185, 58),  nombre,                      font=f_nombre,  fill=(255, 255, 255))
    draw.text((185, 105), f"Servidor:  {servidor}",    font=f_detalle, fill=(180, 185, 220))
    draw.text((185, 140), f"Miembro #  {numero:,}",    font=f_detalle, fill=(180, 185, 220))
    draw.text((185, 168), f"Cuenta creada: {fecha_cuenta}", font=f_detalle, fill=(130, 135, 170))

    buf = io.BytesIO()
    tarjeta.save(buf, "PNG")
    return buf.getvalue()


async def generar_tarjeta_bienvenida(member: discord.Member):
    if not PILLOW_OK:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                str(member.display_avatar.url),
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status != 200:
                    return None
                avatar_bytes = await resp.read()

        nombre      = member.display_name[:24]
        servidor    = member.guild.name[:32]
        numero      = member.guild.member_count
        fecha_cuenta = member.created_at.strftime("%d/%m/%Y")

        loop = asyncio.get_running_loop()
        png_bytes = await loop.run_in_executor(
            None,
            _construir_tarjeta_sync,
            avatar_bytes, nombre, servidor, numero, fecha_cuenta
        )
        return discord.File(fp=io.BytesIO(png_bytes), filename="bienvenida.png")

    except Exception as e:
        logging.getLogger("discord").warning(f"Error generando tarjeta de bienvenida: {e}")
        return None

# --- traducciones (es/en) ---

TEXTOS = {
    "es": {
        "panel_titulo": "⚙️ Panel de Configuración",
        "panel_desc": "Usa los botones para configurar el bot.",
        "roles_mod": "Roles de Moderación",
        "canal_logs": "Canal de Logs",
        "canal_bienvenida": "Canal de Bienvenida",
        "anti_spam": "Anti-Spam",
        "idioma": "Idioma",
        "ninguno": "Ninguno",
        "no_configurado": "No configurado",
        "solo_admin": "Solo los administradores pueden usar este comando.",
        "rol_agregado": "✅ El rol {rol} puede usar comandos de moderación.",
        "rol_quitado": "✅ El rol {rol} ya no puede moderar.",
        "rol_ya_existe": "Ese rol ya está en la lista.",
        "rol_no_existe": "Ese rol no estaba en la lista.",
        "logs_configurado": "✅ Canal de logs: {canal}",
        "bienvenida_configurado": "✅ Canal de bienvenida: {canal}",
        "spam_configurado": "✅ Anti-spam: {limite} mensajes en {segundos} segundos.",
        "idioma_configurado": "✅ Idioma cambiado a Español.",
        "expulsado_spam": "🚫 **{usuario}** fue expulsado por spam.",
        "bienvenida_msg": "¡Bienvenido/a, {usuario}!",
        "bienvenida_desc": "Hola {mencion}, bienvenido/a al servidor.",
        "adios_msg": "**{usuario}** ha salido del servidor.",
        "kick_title": "👢 Kick",
        "ban_title": "🔨 Ban",
        "unban_title": "✅ Unban",
        "mute_title": "🔇 Mute",
        "sin_permisos": "No tienes permisos para usar este comando.",
        "borrados": "Se borraron {n} mensajes.",
        "expulsado": "{usuario} fue expulsado. Razón: {razon}",
        "baneado": "{usuario} fue baneado. Razón: {razon}",
        "desbaneado": "{usuario} fue desbaneado.",
        "silenciado": "{usuario} fue silenciado.",
        "dessilenciado": "{usuario} ya puede hablar de nuevo.",
        "no_baneado": "No encontré ese usuario en la lista de baneados.",
        "no_silenciado": "{usuario} no estaba silenciado.",
        "usuario_field": "Usuario",
        "moderador_field": "Moderador",
        "razon_field": "Razón",
        "accion_field": "Acción",
        "spam_accion": "Expulsado por spam automático",
        "selecciona_rol_add": "Selecciona un rol para agregar como moderador:",
        "selecciona_rol_remove": "Selecciona un rol para quitar de moderadores:",
        "selecciona_canal_logs": "Selecciona el canal de logs:",
        "selecciona_canal_bienvenida": "Selecciona el canal de bienvenida:",
        "spam_invalido": "Formato inválido. Los valores deben ser números mayores a 0.",
        "selecciona_idioma": "Selecciona el idioma / Select language:",
        "mensajes_label": "mensajes en",
        "segundos_label": "segundos",
        "sin_permisos_bot": "No tengo los permisos necesarios para hacer eso. Asegúrate de que mi rol esté por encima del usuario.",
        "rol_muted_creado": "Rol 'Muted' creado automáticamente.",
        "setup_requerido": "⚠️ Primero configura un canal de logs con `/config`.",
        "filtro_agregado": "✅ Palabra `{palabra}` añadida al filtro.",
        "filtro_quitado": "✅ Palabra `{palabra}` quitada del filtro.",
        "filtro_no_existe": "Esa palabra no estaba en el filtro.",
        "filtro_ya_existe": "Esa palabra ya está en el filtro.",
        "filtro_lista": "Palabras filtradas: {lista}",
        "filtro_vacio": "El filtro está vacío.",
        "filtro_detectado": "🚫 Mensaje eliminado por contener palabras prohibidas.",
        "antilink_on": "✅ Anti-links activado.",
        "antilink_off": "✅ Anti-links desactivado.",
        "antilink_detectado": "🚫 Mensaje eliminado por contener un enlace no permitido.",
        "panel_filtro": "Filtro de Palabras",
        "panel_antilink": "Anti-Links",
        "panel_antiraid": "Anti-Raid",
        "estado_on": "✅ Activado",
        "estado_off": "❌ Desactivado",
        "n_palabras": "{n} palabra(s)",
        "raid_info": "`{limite}` joins en `{segundos}` seg",
        "selecciona_antilink": "Activar o desactivar anti-links:",
        "antiraid_configurado": "✅ Anti-raid actualizado: {limite} joins en {segundos}s.",
        "filtro_modal_titulo": "Filtro de Palabras",
        "filtro_modal_label": "Palabra a agregar (deja vacío para solo ver lista)",
        "solo_admin_boton": "Solo el administrador que abrió el panel puede usar estos botones.",
        # Tickets
        "ticket_abierto": "🎫 Ticket abierto en {canal}.",
        "ticket_ya_abierto": "Ya tienes un ticket abierto en {canal}.",
        "ticket_sin_config": "⚠️ El sistema de tickets no está configurado.",
        "ticket_cerrado_msg": "🔒 Ticket cerrado por {usuario}.",
        "ticket_transcript_titulo": "📋 Transcript del ticket",
        "ticket_categoria_soporte": "soporte",
        "ticket_categoria_reporte": "reporte",
        "ticket_categoria_apelacion": "apelacion",
        "ticket_selecciona_tipo": "¿Qué tipo de ticket quieres abrir?",
        "ticket_tipo_soporte": "🛠️ Soporte — Ayuda general",
        "ticket_tipo_reporte": "🚨 Reporte — Reportar a un usuario",
        "ticket_tipo_apelacion": "⚖️ Apelación — Apelar una sanción",
        "ticket_categoria_soporte": "support",
        "ticket_categoria_reporte": "report",
        "ticket_categoria_apelacion": "appeal",
        "ticket_selecciona_tipo": "What type of ticket do you want to open?",
        "ticket_tipo_soporte": "🛠️ Support — General help",
        "ticket_tipo_reporte": "🚨 Report — Report a user",
        "ticket_tipo_apelacion": "⚖️ Appeal — Appeal a sanction",
        "ticket_embed_titulo": "🎫 Ticket #{numero}",
        "ticket_embed_desc": "Hola {mencion}, el equipo de soporte te atenderá en breve.\nUsa el botón para cerrar el ticket cuando termines.",
        "ticket_setup_ok": "✅ Panel de tickets publicado en {canal}.",
        "ticket_panel_titulo": "🎫 Soporte — AegisBot",
        "ticket_panel_desc": "¿Necesitas ayuda o tienes algún problema?\nPresiona el botón para abrir un ticket privado con el equipo de soporte.",
        # Panel de configuración de tickets
        "ticket_cfg_titulo": "🎫 Configuración de Tickets",
        "ticket_cfg_desc": "Configura el sistema de tickets paso a paso.\nUsa los botones para ajustar cada opción.",
        "ticket_cfg_canal": "Canal del Panel",
        "ticket_cfg_categoria": "Categoría",
        "ticket_cfg_logs": "Canal de Logs",
        "ticket_cfg_rol": "Rol de Soporte",
        "ticket_cfg_contador": "Tickets creados",
        "ticket_cfg_sin_canal": "⚠️ Primero selecciona el canal del panel.",
        "ticket_cfg_publicado": "✅ Panel publicado en {canal}.",
        "ticket_cfg_canal_set": "✅ Canal del panel: {canal}",
        "ticket_cfg_categoria_set": "✅ Categoría: {categoria}",
        "ticket_cfg_logs_set": "✅ Canal de logs: {canal}",
        "ticket_cfg_rol_set": "✅ Rol de soporte: {rol}",
        "ticket_cfg_ninguno": "No configurado",
        "selecciona_canal_ticket": "Selecciona el canal del panel:",
        "selecciona_categoria_ticket": "Selecciona la categoría de tickets:",
        "selecciona_logs_ticket": "Selecciona el canal de logs:",
        "selecciona_rol_ticket": "Selecciona el rol de soporte:",
        # Clima
        "clima_error": "❌ No pude obtener el clima para **{ciudad}**. Verifica el nombre de la ciudad.",
        "clima_titulo": "🌤️ Clima en {ciudad}",
        # Define
        "define_error": "❌ No encontré definición para **{palabra}**.",
        "define_titulo": "📖 {palabra}",
        # Meme
        "meme_error": "❌ No pude obtener un meme ahora. Intenta de nuevo.",
        # Giveaway
        "giveaway_error": "❌ No hay giveaways activos ahora mismo. Vuelve a intentarlo más tarde.",
        "giveaway_titulo": "🎮 Giveaways activos",
        "giveaway_worth": "Valor total",
        "giveaway_plataformas": "Plataformas",
        "giveaway_expira": "Expira",
        "giveaway_sin_fecha": "Sin fecha límite",
        "giveaway_usuarios": "usuarios reclamaron",
        "selecciona_canal_giveaway": "Selecciona el canal para el tablero de giveaways:",
        "giveaway_canal_config": "✅ Canal de giveaways: {canal}",
        "panel_giveaway": "Canal Giveaways",
        "giveaway_board_desc": "Lista en vivo · se actualiza cada 15 minutos automáticamente.",
        "giveaway_board_vacio": "No hay giveaways activos ahora mismo. Vuelve más tarde.",
        # AutoMod nuevo
        "antiinvite_on": "✅ Anti-invites activado.",
        "antiinvite_off": "✅ Anti-invites desactivado.",
        "antiinvite_detectado": "🚫 Mensaje eliminado por contener una invitación a otro servidor.",
        "caps_on": "✅ Filtro de mayúsculas activado.",
        "caps_off": "✅ Filtro de mayúsculas desactivado.",
        "caps_detectado": "🔠 Mensaje eliminado por exceso de mayúsculas.",
        "emoji_on": "✅ Filtro de emojis activado.",
        "emoji_off": "✅ Filtro de emojis desactivado.",
        "emoji_detectado": "😶 Mensaje eliminado por spam de emojis.",
        "cuenta_nueva_on": "✅ Alerta de cuentas nuevas activada ({dias} días mínimos).",
        "cuenta_nueva_off": "✅ Alerta de cuentas nuevas desactivada.",
        "cuenta_nueva_alerta_titulo": "⚠️ Cuenta nueva detectada",
        "cuenta_nueva_alerta_desc": "**{mencion}** acaba de unirse y su cuenta tiene menos de **{dias} días**.",
        "cuenta_nueva_dias_label": "Días mínimos de antigüedad",
        "cuenta_nueva_modal_titulo": "Alerta de Cuentas Nuevas",
        "panel_antiinvites": "Anti-Invites",
        "panel_caps": "Filtro Mayúsculas",
        "panel_emoji_filter": "Filtro Emojis",
        "panel_cuenta_nueva": "Cuenta Nueva",
        "cuenta_nueva_info": "{dias}d mínimo",
        "emoji_info": "máx. {n} emojis",
        # Reportes
        "reporte_agregado": "✅ {usuario} ha sido reportado por: {motivo}",
        "reporte_quitado": "✅ Reporte de {usuario} eliminado.",
        "reporte_no_existe": "Ese usuario no tiene reportes activos.",
        "reporte_ya_existe": "Ese usuario ya tiene un reporte activo. Usa `/quitar_reporte` primero.",
        "reporte_lista_vacia": "No hay usuarios reportados en la lista global.",
        "reporte_lista_titulo": "🚨 Lista de usuarios reportados",
        "reporte_alerta_titulo": "⚠️ Usuario marcado se unió",
        "reporte_alerta_desc": "**{mencion}** se unió y está en la lista de reportes globales.",
        "reporte_motivo_label": "Motivo",
        "reporte_reportado_por": "Reportado por",
        "reporte_en_servidor": "En servidor",
        "solo_mod": "Solo moderadores pueden usar este comando.",
    },
    "en": {
        "panel_titulo": "⚙️ Configuration Panel",
        "panel_desc": "Use the buttons to configure the bot.",
        "roles_mod": "Moderation Roles",
        "canal_logs": "Logs Channel",
        "canal_bienvenida": "Welcome Channel",
        "anti_spam": "Anti-Spam",
        "idioma": "Language",
        "ninguno": "None",
        "no_configurado": "Not configured",
        "solo_admin": "Only administrators can use this command.",
        "rol_agregado": "✅ The role {rol} can now use moderation commands.",
        "rol_quitado": "✅ The role {rol} can no longer moderate.",
        "rol_ya_existe": "That role is already in the list.",
        "rol_no_existe": "That role was not in the list.",
        "logs_configurado": "✅ Logs channel: {canal}",
        "bienvenida_configurado": "✅ Welcome channel: {canal}",
        "spam_configurado": "✅ Anti-spam: {limite} messages in {segundos} seconds.",
        "idioma_configurado": "✅ Language changed to English.",
        "expulsado_spam": "🚫 **{usuario}** was kicked for spam.",
        "bienvenida_msg": "Welcome, {usuario}!",
        "bienvenida_desc": "Hey {mencion}, welcome to the server!",
        "adios_msg": "**{usuario}** has left the server.",
        "kick_title": "👢 Kick",
        "ban_title": "🔨 Ban",
        "unban_title": "✅ Unban",
        "mute_title": "🔇 Mute",
        "sin_permisos": "You don't have permission to use this command.",
        "borrados": "{n} messages deleted.",
        "expulsado": "{usuario} was kicked. Reason: {razon}",
        "baneado": "{usuario} was banned. Reason: {razon}",
        "desbaneado": "{usuario} was unbanned.",
        "silenciado": "{usuario} was muted.",
        "dessilenciado": "{usuario} can talk again.",
        "no_baneado": "User not found in the ban list.",
        "no_silenciado": "{usuario} was not muted.",
        "usuario_field": "User",
        "moderador_field": "Moderator",
        "razon_field": "Reason",
        "accion_field": "Action",
        "spam_accion": "Kicked for automatic spam detection",
        "selecciona_rol_add": "Select a role to add as moderator:",
        "selecciona_rol_remove": "Select a role to remove from moderators:",
        "selecciona_canal_logs": "Select the logs channel:",
        "selecciona_canal_bienvenida": "Select the welcome channel:",
        "spam_invalido": "Invalid format. Values must be numbers greater than 0.",
        "selecciona_idioma": "Selecciona el idioma / Select language:",
        "mensajes_label": "messages in",
        "segundos_label": "seconds",
        "sin_permisos_bot": "I don't have the required permissions. Make sure my role is above the target user.",
        "rol_muted_creado": "'Muted' role created automatically.",
        "setup_requerido": "⚠️ Please configure a logs channel first with `/config`.",
        "filtro_agregado": "✅ Word `{palabra}` added to filter.",
        "filtro_quitado": "✅ Word `{palabra}` removed from filter.",
        "filtro_no_existe": "That word was not in the filter.",
        "filtro_ya_existe": "That word is already in the filter.",
        "filtro_lista": "Filtered words: {lista}",
        "filtro_vacio": "The filter is empty.",
        "filtro_detectado": "🚫 Message deleted for containing prohibited words.",
        "antilink_on": "✅ Anti-links enabled.",
        "antilink_off": "✅ Anti-links disabled.",
        "antilink_detectado": "🚫 Message deleted for containing a link.",
        "panel_filtro": "Word Filter",
        "panel_antilink": "Anti-Links",
        "panel_antiraid": "Anti-Raid",
        "estado_on": "✅ Enabled",
        "estado_off": "❌ Disabled",
        "n_palabras": "{n} word(s)",
        "raid_info": "`{limite}` joins in `{segundos}` sec",
        "selecciona_antilink": "Enable or disable anti-links:",
        "antiraid_configurado": "✅ Anti-raid updated: {limite} joins in {segundos}s.",
        "filtro_modal_titulo": "Word Filter",
        "filtro_modal_label": "Word to add (leave empty to only view list)",
        "solo_admin_boton": "Only the administrator who opened the panel can use these buttons.",
        # Tickets
        "ticket_abierto": "🎫 Ticket opened in {canal}.",
        "ticket_ya_abierto": "You already have an open ticket in {canal}.",
        "ticket_sin_config": "⚠️ The ticket system is not configured.",
        "ticket_cerrado_msg": "🔒 Ticket closed by {usuario}.",
        "ticket_transcript_titulo": "📋 Ticket transcript",
        "ticket_embed_titulo": "🎫 Ticket #{numero}",
        "ticket_embed_desc": "Hello {mencion}, the support team will assist you shortly.\nUse the button to close the ticket when you're done.",
        "ticket_setup_ok": "✅ Ticket panel posted in {canal}.",
        "ticket_panel_titulo": "🎫 Support — AegisBot",
        "ticket_panel_desc": "Need help or have an issue?\nPress the button to open a private ticket with the support team.",
        # Ticket setup panel
        "ticket_cfg_titulo": "🎫 Ticket Setup",
        "ticket_cfg_desc": "Configure the ticket system step by step.\nUse the buttons to adjust each option.",
        "ticket_cfg_canal": "Panel Channel",
        "ticket_cfg_categoria": "Category",
        "ticket_cfg_logs": "Logs Channel",
        "ticket_cfg_rol": "Support Role",
        "ticket_cfg_contador": "Tickets created",
        "ticket_cfg_sin_canal": "⚠️ Select the panel channel first.",
        "ticket_cfg_publicado": "✅ Panel published in {canal}.",
        "ticket_cfg_canal_set": "✅ Panel channel: {canal}",
        "ticket_cfg_categoria_set": "✅ Category: {categoria}",
        "ticket_cfg_logs_set": "✅ Logs channel: {canal}",
        "ticket_cfg_rol_set": "✅ Support role: {rol}",
        "ticket_cfg_ninguno": "Not configured",
        "selecciona_canal_ticket": "Select the panel channel:",
        "selecciona_categoria_ticket": "Select the ticket category:",
        "selecciona_logs_ticket": "Select the logs channel:",
        "selecciona_rol_ticket": "Select the support role:",
        # Clima
        "clima_error": "❌ Could not get weather for **{ciudad}**. Check the city name.",
        "clima_titulo": "🌤️ Weather in {ciudad}",
        # Define
        "define_error": "❌ No definition found for **{palabra}**.",
        "define_titulo": "📖 {palabra}",
        # Meme
        "meme_error": "❌ Could not fetch a meme right now. Try again.",
        # Giveaway
        "giveaway_error": "❌ No active giveaways right now. Try again later.",
        "giveaway_titulo": "🎮 Active giveaways",
        "giveaway_worth": "Total worth",
        "giveaway_plataformas": "Platforms",
        "giveaway_expira": "Expires",
        "giveaway_sin_fecha": "No expiry date",
        "giveaway_usuarios": "users claimed",
        "selecciona_canal_giveaway": "Select the channel for the giveaway board:",
        "giveaway_canal_config": "✅ Giveaway channel: {canal}",
        "panel_giveaway": "Giveaway Channel",
        "giveaway_board_desc": "Live list · updates every 15 minutes automatically.",
        "giveaway_board_vacio": "No active giveaways right now. Check back later.",
        # AutoMod nuevo
        "antiinvite_on": "✅ Anti-invites enabled.",
        "antiinvite_off": "✅ Anti-invites disabled.",
        "antiinvite_detectado": "🚫 Message deleted for containing an invite to another server.",
        "caps_on": "✅ Caps filter enabled.",
        "caps_off": "✅ Caps filter disabled.",
        "caps_detectado": "🔠 Message deleted for excessive caps.",
        "emoji_on": "✅ Emoji filter enabled.",
        "emoji_off": "✅ Emoji filter disabled.",
        "emoji_detectado": "😶 Message deleted for emoji spam.",
        "cuenta_nueva_on": "✅ New account alert enabled ({dias} day minimum).",
        "cuenta_nueva_off": "✅ New account alert disabled.",
        "cuenta_nueva_alerta_titulo": "⚠️ New account detected",
        "cuenta_nueva_alerta_desc": "**{mencion}** just joined and their account is less than **{dias} days** old.",
        "cuenta_nueva_dias_label": "Minimum account age in days",
        "cuenta_nueva_modal_titulo": "New Account Alert",
        "panel_antiinvites": "Anti-Invites",
        "panel_caps": "Caps Filter",
        "panel_emoji_filter": "Emoji Filter",
        "panel_cuenta_nueva": "New Account",
        "cuenta_nueva_info": "{dias}d minimum",
        "emoji_info": "max. {n} emojis",
        # Reports
        "reporte_agregado": "✅ {usuario} has been reported for: {motivo}",
        "reporte_quitado": "✅ Report for {usuario} removed.",
        "reporte_no_existe": "That user has no active reports.",
        "reporte_ya_existe": "That user already has an active report. Use `/quitar_reporte` first.",
        "reporte_lista_vacia": "No reported users in the global list.",
        "reporte_lista_titulo": "🚨 Reported users list",
        "reporte_alerta_titulo": "⚠️ Flagged user joined",
        "reporte_alerta_desc": "**{mencion}** just joined and is on the global report list.",
        "reporte_motivo_label": "Reason",
        "reporte_reportado_por": "Reported by",
        "reporte_en_servidor": "On server",
        "solo_mod": "Only moderators can use this command.",
    }
}

def t(guild_id, clave, **kwargs):
    cfg = get_guild_config(guild_id)
    idioma = cfg.get("idioma", "es")
    texto = TEXTOS.get(idioma, TEXTOS["es"]).get(clave, clave)
    return texto.format(**kwargs) if kwargs else texto

# --- config por servidor ---

CONFIG_FILE    = "server_config.json"
REPORTES_FILE  = "reportes_globales.json"

def cargar_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def _guardar_atomico(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=4)
    os.replace(tmp, path)

def guardar_config(data):
    _guardar_atomico(CONFIG_FILE, data)

_config_lock = asyncio.Lock()

async def guardar_config_async():
    async with _config_lock:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _guardar_atomico, CONFIG_FILE, server_config)
        except Exception as e:
            logger.error(f"Error guardando config: {e}")

def _cargar_reportes_file() -> dict:
    if os.path.exists(REPORTES_FILE):
        try:
            with open(REPORTES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _guardar_reportes_file(data: dict):
    _guardar_atomico(REPORTES_FILE, data)

_reportes_lock = asyncio.Lock()

async def guardar_reportes_async():
    async with _reportes_lock:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, _guardar_atomico, REPORTES_FILE, reportes_globales)
        except Exception as e:
            logger.error(f"Error guardando reportes: {e}")

server_config    = cargar_config()
reportes_globales: dict = _cargar_reportes_file()

# Migración: si había reportes en server_config bajo __reportes__, moverlos
if "__reportes__" in server_config:
    _migrados = server_config.pop("__reportes__", {})
    for uid, info in _migrados.items():
        if uid not in reportes_globales:
            reportes_globales[uid] = info
    _guardar_reportes_file(reportes_globales)
    guardar_config(server_config)

def get_guild_config(guild_id):
    gid = str(guild_id)
    if gid not in server_config:
        server_config[gid] = {
            "roles_mod": [],
            "canal_logs": None,
            "canal_bienvenida": None,
            "spam_limite": 5,
            "spam_segundos": 5,
            "idioma": "es",
            "filtro_palabras": [],
            "anti_links": False,
            "anti_raid": False,
            "raid_limite": 10,
            "raid_segundos": 10
        }
        guardar_config(server_config)
    cfg = server_config[gid]
    campos_faltantes = False
    for campo, valor in [
        ("filtro_palabras", []),
        ("anti_links", False),
        ("anti_raid", False),
        ("raid_limite", 10),
        ("raid_segundos", 10),
        ("ticket_canal_soporte", None),
        ("ticket_categoria", None),
        ("ticket_logs", None),
        ("ticket_rol_soporte", None),
        ("ticket_contador", 0),
        ("giveaway_canal", None),
        ("giveaway_message_id", None),
        ("anti_invites", False),
        ("caps_filter", False),
        ("caps_porcentaje", 70),
        ("emoji_filter", False),
        ("emoji_limite", 10),
        ("cuenta_nueva", False),
        ("cuenta_nueva_dias", 7),
    ]:
        if campo not in cfg:
            cfg[campo] = valor
            campos_faltantes = True
    if campos_faltantes:
        guardar_config(server_config)
    return server_config[gid]

# --- logging ---

def setup_logging():
    logger = logging.getLogger('discord')
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)
    return logger

logger = setup_logging()

# intents mínimos necesarios: message_content para automod, members para joins/bienvenida
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=CONFIG["PREFIX"], intents=intents)

# --- helpers ---

def tiene_permiso_mod(member, guild_config):
    if member.guild_permissions.administrator:
        return True
    roles_mod = guild_config.get("roles_mod", [])
    return any(str(role.id) in roles_mod for role in member.roles)

async def enviar_log(guild, embed):
    cfg = get_guild_config(guild.id)
    canal_id = cfg.get("canal_logs")
    if canal_id:
        canal = guild.get_channel(int(canal_id))
        if canal:
            try:
                await canal.send(embed=embed)
                return
            except discord.Forbidden:
                pass
    # Sin canal de logs configurado → buscar o crear canal privado solo para admins
    try:
        canal_admin = discord.utils.get(guild.text_channels, name="aegis-logs")
        if not canal_admin:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }
            for member in guild.members:
                if member.guild_permissions.administrator and not member.bot:
                    overwrites[member] = discord.PermissionOverwrite(read_messages=True)
            canal_admin = await guild.create_text_channel(
                "aegis-logs",
                overwrites=overwrites,
                reason="Canal de logs automático de AegisBot"
            )
        await canal_admin.send(embed=embed)
    except Exception as e:
        logger.warning(f"enviar_log fallback fallido en {guild.name}: {e}")

async def obtener_o_crear_rol_muted(guild):
    rol_mute = discord.utils.get(guild.roles, name="Muted")
    if not rol_mute:
        try:
            rol_mute = await guild.create_role(name="Muted", reason="Creado por el bot para silenciar usuarios.")
            for canal in guild.text_channels:
                try:
                    await canal.set_permissions(rol_mute, send_messages=False, add_reactions=False)
                except discord.Forbidden:
                    pass
            for canal in guild.voice_channels:
                try:
                    await canal.set_permissions(rol_mute, speak=False)
                except discord.Forbidden:
                    pass
        except discord.Forbidden:
            return None
    return rol_mute

def build_panel_embed(guild):
    cfg = get_guild_config(guild.id)
    gid = guild.id

    roles_mod = cfg.get("roles_mod", [])
    roles_texto = ", ".join([f"<@&{r}>" for r in roles_mod]) if roles_mod else t(gid, "ninguno")
    logs_id = cfg.get("canal_logs")
    logs_texto = f"<#{logs_id}>" if logs_id else t(gid, "no_configurado")
    bienvenida_id = cfg.get("canal_bienvenida")
    bienvenida_texto = f"<#{bienvenida_id}>" if bienvenida_id else t(gid, "no_configurado")
    spam_limite = cfg.get("spam_limite", 5)
    spam_segundos = cfg.get("spam_segundos", 5)
    idioma_actual = "🇪🇸 Español" if cfg.get("idioma", "es") == "es" else "🇺🇸 English"
    # AutoMod
    n_filtro = len(cfg.get("filtro_palabras", []))
    filtro_texto = t(gid, "n_palabras", n=n_filtro) if n_filtro else t(gid, "ninguno")
    antilink_texto = t(gid, "estado_on") if cfg.get("anti_links", False) else t(gid, "estado_off")
    antiraid_on = cfg.get("anti_raid", False)
    if antiraid_on:
        antiraid_texto = t(gid, "raid_info", limite=cfg.get("raid_limite", 10), segundos=cfg.get("raid_segundos", 10))
    else:
        antiraid_texto = t(gid, "estado_off")

    embed = discord.Embed(
        title=t(gid, "panel_titulo"),
        description=f"╔══════════════════════════╗\n║  {t(gid, 'panel_desc')}  ║\n╚══════════════════════════╝",
        color=COLORS["panel"]
    )
    embed.add_field(name=f"🛡️ {t(gid, 'roles_mod')}", value=roles_texto, inline=False)
    embed.add_field(name=f"📋 {t(gid, 'canal_logs')}", value=logs_texto, inline=True)
    embed.add_field(name=f"👋 {t(gid, 'canal_bienvenida')}", value=bienvenida_texto, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.add_field(name=f"🚫 {t(gid, 'anti_spam')}", value=f"`{spam_limite}` {t(gid, 'mensajes_label')} `{spam_segundos}` {t(gid, 'segundos_label')}", inline=True)
    embed.add_field(name=f"🌐 {t(gid, 'idioma')}", value=idioma_actual, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.add_field(name=f"🔤 {t(gid, 'panel_filtro')}", value=filtro_texto, inline=True)
    embed.add_field(name=f"🔗 {t(gid, 'panel_antilink')}", value=antilink_texto, inline=True)
    embed.add_field(name=f"🚨 {t(gid, 'panel_antiraid')}", value=antiraid_texto, inline=True)
    giveaway_canal_id = cfg.get("giveaway_canal")
    giveaway_texto = f"<#{giveaway_canal_id}>" if giveaway_canal_id else t(gid, "no_configurado")
    embed.add_field(name=f"🎮 {t(gid, 'panel_giveaway')}", value=giveaway_texto, inline=True)
    # AutoMod avanzado
    antiinvite_texto = t(gid, "estado_on") if cfg.get("anti_invites", False) else t(gid, "estado_off")
    caps_texto = t(gid, "estado_on") if cfg.get("caps_filter", False) else t(gid, "estado_off")
    emoji_on = cfg.get("emoji_filter", False)
    emoji_texto = t(gid, "emoji_info", n=cfg.get("emoji_limite", 10)) if emoji_on else t(gid, "estado_off")
    cuenta_on = cfg.get("cuenta_nueva", False)
    cuenta_texto = t(gid, "cuenta_nueva_info", dias=cfg.get("cuenta_nueva_dias", 7)) if cuenta_on else t(gid, "estado_off")
    embed.add_field(name=f"📨 {t(gid, 'panel_antiinvites')}", value=antiinvite_texto, inline=True)
    embed.add_field(name=f"🔠 {t(gid, 'panel_caps')}", value=caps_texto, inline=True)
    embed.add_field(name=f"😶 {t(gid, 'panel_emoji_filter')}", value=emoji_texto, inline=True)
    embed.add_field(name=f"🆕 {t(gid, 'panel_cuenta_nueva')}", value=cuenta_texto, inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=f"{guild.name} • Configuración del servidor", icon_url=guild.icon.url if guild.icon else None)
    embed.timestamp = discord.utils.utcnow()
    return embed

# ==================================================================================================
# --- SELECTORES ---
# ==================================================================================================

class RolModAddSelect(ui.Select):
    def __init__(self, guild, panel_message):
        self.guild_id = guild.id
        self.panel_message = panel_message
        opciones = [
            discord.SelectOption(label=rol.name[:100], value=str(rol.id))
            for rol in guild.roles
            if not rol.is_bot_managed() and rol.name != "@everyone"
        ][:25]
        if not opciones:
            opciones = [discord.SelectOption(label="Sin roles disponibles", value="none")]
        super().__init__(placeholder=t(guild.id, "selecciona_rol_add"), options=opciones, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No hay roles disponibles.", ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        rol_id = self.values[0]
        if rol_id not in cfg["roles_mod"]:
            cfg["roles_mod"].append(rol_id)
            await guardar_config_async()
            rol = interaction.guild.get_role(int(rol_id))
            msg = t(self.guild_id, "rol_agregado", rol=rol.mention if rol else rol_id)
        else:
            msg = t(self.guild_id, "rol_ya_existe")
        await interaction.response.send_message(msg, ephemeral=True)
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=build_panel_embed(interaction.guild))
            except Exception as e:
                logger.warning(f"No se pudo actualizar panel: {e}")

class RolModRemoveSelect(ui.Select):
    def __init__(self, guild, panel_message):
        self.guild_id = guild.id
        self.panel_message = panel_message
        cfg = get_guild_config(guild.id)
        roles_mod = cfg.get("roles_mod", [])
        opciones = []
        for rol_id in roles_mod:
            rol = guild.get_role(int(rol_id))
            if rol:
                opciones.append(discord.SelectOption(label=rol.name[:100], value=rol_id))
        if not opciones:
            opciones = [discord.SelectOption(label="Sin roles configurados", value="none")]
        super().__init__(placeholder=t(guild.id, "selecciona_rol_remove"), options=opciones, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No hay roles moderadores configurados.", ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        rol_id = self.values[0]
        if rol_id in cfg["roles_mod"]:
            cfg["roles_mod"].remove(rol_id)
            await guardar_config_async()
            rol = interaction.guild.get_role(int(rol_id))
            msg = t(self.guild_id, "rol_quitado", rol=rol.mention if rol else rol_id)
        else:
            msg = t(self.guild_id, "rol_no_existe")
        await interaction.response.send_message(msg, ephemeral=True)
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=build_panel_embed(interaction.guild))
            except Exception as e:
                logger.warning(f"No se pudo actualizar panel: {e}")

class CanalLogsSelect(ui.Select):
    def __init__(self, guild, panel_message):
        self.guild_id = guild.id
        self.panel_message = panel_message
        opciones = [
            discord.SelectOption(label=f"# {canal.name}"[:100], value=str(canal.id))
            for canal in guild.text_channels
        ][:25]
        if not opciones:
            opciones = [discord.SelectOption(label="Sin canales disponibles", value="none")]
        super().__init__(placeholder=t(guild.id, "selecciona_canal_logs"), options=opciones, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No hay canales disponibles.", ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        canal_id = self.values[0]
        cfg["canal_logs"] = canal_id
        await guardar_config_async()
        canal = interaction.guild.get_channel(int(canal_id))
        await interaction.response.send_message(
            t(self.guild_id, "logs_configurado", canal=canal.mention if canal else canal_id), ephemeral=True
        )
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=build_panel_embed(interaction.guild))
            except Exception as e:
                logger.warning(f"No se pudo actualizar panel: {e}")

class CanalBienvenidaSelect(ui.Select):
    def __init__(self, guild, panel_message):
        self.guild_id = guild.id
        self.panel_message = panel_message
        opciones = [
            discord.SelectOption(label=f"# {canal.name}"[:100], value=str(canal.id))
            for canal in guild.text_channels
        ][:25]
        if not opciones:
            opciones = [discord.SelectOption(label="Sin canales disponibles", value="none")]
        super().__init__(placeholder=t(guild.id, "selecciona_canal_bienvenida"), options=opciones, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No hay canales disponibles.", ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        canal_id = self.values[0]
        cfg["canal_bienvenida"] = canal_id
        await guardar_config_async()
        canal = interaction.guild.get_channel(int(canal_id))
        await interaction.response.send_message(
            t(self.guild_id, "bienvenida_configurado", canal=canal.mention if canal else canal_id), ephemeral=True
        )
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=build_panel_embed(interaction.guild))
            except Exception as e:
                logger.warning(f"No se pudo actualizar panel: {e}")

class CanalGiveawaySelect(ui.Select):
    def __init__(self, guild, panel_message):
        self.guild_id = guild.id
        self.panel_message = panel_message
        opciones = [
            discord.SelectOption(label=f"# {canal.name}"[:100], value=str(canal.id))
            for canal in guild.text_channels
        ][:25]
        if not opciones:
            opciones = [discord.SelectOption(label="Sin canales disponibles", value="none")]
        super().__init__(placeholder=t(guild.id, "selecciona_canal_giveaway"), options=opciones, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No hay canales disponibles.", ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        canal_id = self.values[0]
        cfg["giveaway_canal"] = canal_id
        cfg["giveaway_message_id"] = None  # Resetear: se enviará mensaje nuevo en el próximo ciclo
        await guardar_config_async()
        canal = interaction.guild.get_channel(int(canal_id))
        await interaction.response.send_message(
            t(self.guild_id, "giveaway_canal_config", canal=canal.mention if canal else canal_id), ephemeral=True
        )
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=build_panel_embed(interaction.guild))
            except Exception as e:
                logger.warning(f"No se pudo actualizar panel: {e}")

class IdiomaSelect(ui.Select):
    def __init__(self, guild_id, panel_message, authorized_user_id=None):
        options = [
            discord.SelectOption(label="🇪🇸 Español", value="es"),
            discord.SelectOption(label="🇺🇸 English", value="en"),
        ]
        super().__init__(placeholder=t(guild_id, "selecciona_idioma"), options=options, min_values=1, max_values=1)
        self.guild_id = guild_id
        self.panel_message = panel_message
        self.authorized_user_id = authorized_user_id

    async def callback(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        cfg["idioma"] = self.values[0]
        await guardar_config_async()
        await interaction.response.send_message(t(self.guild_id, "idioma_configurado"), ephemeral=True)
        if self.panel_message:
            try:
                await self.panel_message.edit(
                    embed=build_panel_embed(interaction.guild),
                    view=ConfigView(interaction.guild, self.panel_message, authorized_user_id=self.authorized_user_id)
                )
            except Exception as e:
                logger.warning(f"No se pudo actualizar panel: {e}")

class SpamModal(ui.Modal):
    def __init__(self, guild_id, panel_message):
        super().__init__(title="Anti-Spam")
        self.guild_id = guild_id
        self.panel_message = panel_message
        cfg = get_guild_config(guild_id)
        self.limite = ui.TextInput(label="Mensajes / Messages", default=str(cfg.get("spam_limite", 5)), max_length=3)
        self.segundos = ui.TextInput(label="Segundos / Seconds", default=str(cfg.get("spam_segundos", 5)), max_length=3)
        self.add_item(self.limite)
        self.add_item(self.segundos)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limite = int(self.limite.value)
            segundos = int(self.segundos.value)
            if limite < 2 or segundos < 1:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(t(self.guild_id, "spam_invalido"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        cfg["spam_limite"] = limite
        cfg["spam_segundos"] = segundos
        await guardar_config_async()
        await interaction.response.send_message(
            t(self.guild_id, "spam_configurado", limite=limite, segundos=segundos),
            ephemeral=True
        )
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=build_panel_embed(interaction.guild))
            except Exception as e:
                logger.warning(f"No se pudo actualizar panel: {e}")

class FiltroModal(ui.Modal):
    def __init__(self, guild_id, panel_message):
        super().__init__(title=t(guild_id, "filtro_modal_titulo"))
        self.guild_id = guild_id
        self.panel_message = panel_message
        self.palabra_input = ui.TextInput(
            label="Agregar palabra / Add word",
            placeholder="Escribe una palabra para añadir al filtro...",
            required=False,
            max_length=50
        )
        self.quitar_input = ui.TextInput(
            label="Quitar palabra / Remove word",
            placeholder="Escribe una palabra para quitarla del filtro...",
            required=False,
            max_length=50
        )
        self.add_item(self.palabra_input)
        self.add_item(self.quitar_input)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_guild_config(self.guild_id)
        gid = self.guild_id
        msgs = []

        agregar = self.palabra_input.value.lower().strip()
        quitar = self.quitar_input.value.lower().strip()

        if agregar:
            if agregar not in cfg["filtro_palabras"]:
                cfg["filtro_palabras"].append(agregar)
                await guardar_config_async()
                msgs.append(t(gid, "filtro_agregado", palabra=agregar))
            else:
                msgs.append(t(gid, "filtro_ya_existe"))

        if quitar:
            if quitar in cfg["filtro_palabras"]:
                cfg["filtro_palabras"].remove(quitar)
                await guardar_config_async()
                msgs.append(t(gid, "filtro_quitado", palabra=quitar))
            else:
                msgs.append(t(gid, "filtro_no_existe"))

        lista = cfg.get("filtro_palabras", [])
        lista_txt = t(gid, "filtro_lista", lista=", ".join(f"`{p}`" for p in lista)) if lista else t(gid, "filtro_vacio")
        msgs.append(lista_txt)

        await interaction.response.send_message("\n".join(msgs), ephemeral=True)
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=build_panel_embed(interaction.guild))
            except Exception as e:
                logger.warning(f"No se pudo actualizar panel: {e}")

class AntiRaidModal(ui.Modal):
    def __init__(self, guild_id, panel_message):
        super().__init__(title="Anti-Raid")
        self.guild_id = guild_id
        self.panel_message = panel_message
        cfg = get_guild_config(guild_id)
        self.limite = ui.TextInput(label="Joins para activar / Joins to trigger", default=str(cfg.get("raid_limite", 10)), max_length=3)
        self.segundos = ui.TextInput(label="Ventana en segundos / Window in seconds", default=str(cfg.get("raid_segundos", 10)), max_length=3)
        self.add_item(self.limite)
        self.add_item(self.segundos)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limite = max(3, int(self.limite.value))
            segundos = max(3, int(self.segundos.value))
        except ValueError:
            await interaction.response.send_message(t(self.guild_id, "spam_invalido"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        cfg["anti_raid"] = True
        cfg["raid_limite"] = limite
        cfg["raid_segundos"] = segundos
        await guardar_config_async()
        await interaction.response.send_message(
            t(self.guild_id, "antiraid_configurado", limite=limite, segundos=segundos),
            ephemeral=True
        )
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=build_panel_embed(interaction.guild))
            except Exception as e:
                logger.warning(f"No se pudo actualizar panel: {e}")

# --- modales ---

class EmojiFilterModal(ui.Modal):
    def __init__(self, guild_id, panel_message):
        super().__init__(title="Filtro de Emojis / Emoji Filter")
        self.guild_id = guild_id
        self.panel_message = panel_message
        cfg = get_guild_config(guild_id)
        self.limite = ui.TextInput(
            label="Máx. emojis por mensaje / Max emojis per msg",
            default=str(cfg.get("emoji_limite", 10)),
            max_length=3
        )
        self.add_item(self.limite)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limite = int(self.limite.value)
            if limite < 1:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(t(self.guild_id, "spam_invalido"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        cfg["emoji_filter"] = True
        cfg["emoji_limite"] = limite
        await guardar_config_async()
        await interaction.response.send_message(
            t(self.guild_id, "emoji_on"), ephemeral=True
        )
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=build_panel_embed(interaction.guild))
            except Exception as e:
                logger.warning(f"No se pudo actualizar panel: {e}")

class CuentaNuevaModal(ui.Modal):
    def __init__(self, guild_id, panel_message):
        super().__init__(title=t(guild_id, "cuenta_nueva_modal_titulo"))
        self.guild_id = guild_id
        self.panel_message = panel_message
        cfg = get_guild_config(guild_id)
        self.dias = ui.TextInput(
            label=t(guild_id, "cuenta_nueva_dias_label"),
            default=str(cfg.get("cuenta_nueva_dias", 7)),
            max_length=3
        )
        self.add_item(self.dias)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            dias = int(self.dias.value)
            if dias < 1:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(t(self.guild_id, "spam_invalido"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        cfg["cuenta_nueva"] = True
        cfg["cuenta_nueva_dias"] = dias
        await guardar_config_async()
        await interaction.response.send_message(
            t(self.guild_id, "cuenta_nueva_on", dias=dias), ephemeral=True
        )
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=build_panel_embed(interaction.guild))
            except Exception as e:
                logger.warning(f"No se pudo actualizar panel: {e}")

# --- panel de configuración ---

class ConfigView(ui.View):
    def __init__(self, guild, panel_message=None, authorized_user_id=None):
        super().__init__(timeout=300)
        self.guild = guild
        self.panel_message = panel_message
        self.authorized_user_id = authorized_user_id

    def _check_user(self, interaction: discord.Interaction) -> bool:
        """Devuelve True si el usuario está autorizado."""
        return self.authorized_user_id is None or interaction.user.id == self.authorized_user_id

    @ui.button(label="🛡️ Agregar Rol Mod", style=discord.ButtonStyle.primary, row=0)
    async def btn_add_rol(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        view = ui.View(timeout=60)
        view.add_item(RolModAddSelect(self.guild, self.panel_message))
        await interaction.response.send_message(t(self.guild.id, "selecciona_rol_add"), view=view, ephemeral=True)

    @ui.button(label="➖ Quitar Rol Mod", style=discord.ButtonStyle.secondary, row=0)
    async def btn_remove_rol(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        view = ui.View(timeout=60)
        view.add_item(RolModRemoveSelect(self.guild, self.panel_message))
        await interaction.response.send_message(t(self.guild.id, "selecciona_rol_remove"), view=view, ephemeral=True)

    @ui.button(label="📋 Canal Logs", style=discord.ButtonStyle.primary, row=1)
    async def btn_logs(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        view = ui.View(timeout=60)
        view.add_item(CanalLogsSelect(self.guild, self.panel_message))
        await interaction.response.send_message(t(self.guild.id, "selecciona_canal_logs"), view=view, ephemeral=True)

    @ui.button(label="👋 Canal Bienvenida", style=discord.ButtonStyle.primary, row=1)
    async def btn_bienvenida(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        view = ui.View(timeout=60)
        view.add_item(CanalBienvenidaSelect(self.guild, self.panel_message))
        await interaction.response.send_message(t(self.guild.id, "selecciona_canal_bienvenida"), view=view, ephemeral=True)

    @ui.button(label="🎮 Canal Giveaways", style=discord.ButtonStyle.primary, row=1)
    async def btn_giveaway_canal(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        view = ui.View(timeout=60)
        view.add_item(CanalGiveawaySelect(self.guild, self.panel_message))
        await interaction.response.send_message(t(self.guild.id, "selecciona_canal_giveaway"), view=view, ephemeral=True)

    @ui.button(label="🚫 Anti-Spam", style=discord.ButtonStyle.danger, row=2)
    async def btn_spam(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        await interaction.response.send_modal(SpamModal(self.guild.id, self.panel_message))

    @ui.button(label="🌐 Idioma / Language", style=discord.ButtonStyle.secondary, row=2)
    async def btn_idioma(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        gid = self.guild.id
        view = ui.View(timeout=60)
        view.add_item(IdiomaSelect(gid, self.panel_message, authorized_user_id=self.authorized_user_id))
        await interaction.response.send_message(t(gid, "selecciona_idioma"), view=view, ephemeral=True)

    @ui.button(label="🔤 Filtro Palabras", style=discord.ButtonStyle.danger, row=3)
    async def btn_filtro(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        await interaction.response.send_modal(FiltroModal(self.guild.id, self.panel_message))

    @ui.button(label="🔗 Anti-Links", style=discord.ButtonStyle.secondary, row=3)
    async def btn_antilink(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild.id)
        cfg["anti_links"] = not cfg.get("anti_links", False)
        await guardar_config_async()
        estado = "antilink_on" if cfg["anti_links"] else "antilink_off"
        nuevo_embed = build_panel_embed(self.guild)
        await interaction.response.edit_message(embed=nuevo_embed, view=self)
        await interaction.followup.send(t(self.guild.id, estado), ephemeral=True)

    @ui.button(label="🚨 Anti-Raid", style=discord.ButtonStyle.danger, row=3)
    async def btn_antiraid(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild.id)
        if cfg.get("anti_raid", False):
            cfg["anti_raid"] = False
            await guardar_config_async()
            nuevo_embed = build_panel_embed(self.guild)
            await interaction.response.edit_message(embed=nuevo_embed, view=self)
            await interaction.followup.send("🛡️ Anti-Raid desactivado.", ephemeral=True)
        else:
            await interaction.response.send_modal(AntiRaidModal(self.guild.id, self.panel_message))

    @ui.button(label="📨 Anti-Invites", style=discord.ButtonStyle.secondary, row=3)
    async def btn_antiinvites(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild.id)
        cfg["anti_invites"] = not cfg.get("anti_invites", False)
        await guardar_config_async()
        estado = "antiinvite_on" if cfg["anti_invites"] else "antiinvite_off"
        nuevo_embed = build_panel_embed(self.guild)
        await interaction.response.edit_message(embed=nuevo_embed, view=self)
        await interaction.followup.send(t(self.guild.id, estado), ephemeral=True)

    @ui.button(label="🔠 Caps Filter", style=discord.ButtonStyle.secondary, row=4)
    async def btn_caps(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild.id)
        cfg["caps_filter"] = not cfg.get("caps_filter", False)
        await guardar_config_async()
        estado = "caps_on" if cfg["caps_filter"] else "caps_off"
        nuevo_embed = build_panel_embed(self.guild)
        await interaction.response.edit_message(embed=nuevo_embed, view=self)
        await interaction.followup.send(t(self.guild.id, estado), ephemeral=True)

    @ui.button(label="😶 Emoji Filter", style=discord.ButtonStyle.secondary, row=4)
    async def btn_emoji_filter(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild.id)
        if cfg.get("emoji_filter", False):
            # Está activo → desactivar
            cfg["emoji_filter"] = False
            await guardar_config_async()
            nuevo_embed = build_panel_embed(self.guild)
            await interaction.response.edit_message(embed=nuevo_embed, view=self)
            await interaction.followup.send(t(self.guild.id, "emoji_off"), ephemeral=True)
        else:
            # Está inactivo → modal para configurar límite
            await interaction.response.send_modal(EmojiFilterModal(self.guild.id, self.panel_message))

    @ui.button(label="🆕 Cuenta Nueva", style=discord.ButtonStyle.secondary, row=4)
    async def btn_cuenta_nueva(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild.id)
        if cfg.get("cuenta_nueva", False):
            # Está activo → desactivar
            cfg["cuenta_nueva"] = False
            await guardar_config_async()
            nuevo_embed = build_panel_embed(self.guild)
            await interaction.response.edit_message(embed=nuevo_embed, view=self)
            await interaction.followup.send(t(self.guild.id, "cuenta_nueva_off"), ephemeral=True)
        else:
            # Está inactivo → modal para configurar días
            await interaction.response.send_modal(CuentaNuevaModal(self.guild.id, self.panel_message))

    @ui.button(label="❌ Cerrar", style=discord.ButtonStyle.danger, row=4)
    async def btn_cerrar(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check_user(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        await interaction.response.edit_message(content="✅ Panel cerrado.", embed=None, view=None)

# --- logs de mensajes en archivo ---
# Los mensajes eliminados/editados van a message_logs/<guild_id>.txt, no a Discord.

URL_REGEX    = re.compile(r"https?://\S+|www\.\S+|discord\.gg/\S+", re.IGNORECASE)
INVITE_REGEX = re.compile(r"discord\.gg/\S+|discord(?:app)?\.com/invite/\S+", re.IGNORECASE)
EMOJI_REGEX  = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\u2640-\u2642\u2600-\u2B55\u200d\u23cf\u23e9\u231a\ufe0f\u3030]+",
    re.UNICODE
)

def _log_mensaje_sync(entrada: str, nombre_archivo: str):
    try:
        with open(nombre_archivo, "a", encoding="utf-8") as f:
            f.write(entrada)
    except Exception as e:
        logger.error(f"Error escribiendo log de mensajes: {e}")

def log_mensaje_archivo(tipo: str, guild_id: int, guild_name: str, canal_name: str,
                        usuario: str, usuario_id: int, contenido_antes: str, contenido_despues: str = None):
    fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    nombre_archivo = os.path.join(LOGS_DIR, f"{guild_id}.txt")
    linea_sep = "-" * 60

    if tipo == "eliminado":
        entrada = (
            f"\n{linea_sep}\n"
            f"[{fecha}] MENSAJE ELIMINADO\n"
            f"Servidor : {guild_name} ({guild_id})\n"
            f"Canal    : #{canal_name}\n"
            f"Usuario  : {usuario} ({usuario_id})\n"
            f"Contenido: {contenido_antes}\n"
        )
    elif tipo == "editado":
        entrada = (
            f"\n{linea_sep}\n"
            f"[{fecha}] MENSAJE EDITADO\n"
            f"Servidor : {guild_name} ({guild_id})\n"
            f"Canal    : #{canal_name}\n"
            f"Usuario  : {usuario} ({usuario_id})\n"
            f"Antes    : {contenido_antes}\n"
            f"Después  : {contenido_despues}\n"
        )
    else:
        return

    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _log_mensaje_sync, entrada, nombre_archivo)
    except RuntimeError:
        _log_mensaje_sync(entrada, nombre_archivo)

# --- anti-spam ---

spam_tracker = defaultdict(list)
# contador de slowmode por canal: {canal_id: nivel} — sube con cada detección, baja solo
slowmode_tracker: dict = defaultdict(int)
SLOWMODE_NIVELES = [5, 30, 60, 120]  # segundos por nivel

async def verificar_spam(message):
    cfg = get_guild_config(message.guild.id)
    limite = cfg.get("spam_limite", 5)
    ventana = cfg.get("spam_segundos", 5)
    gid = message.guild.id

    # clave compuesta para separar tracking por servidor
    key = (gid, message.author.id)
    user_id = message.author.id
    ahora = time.time()

    spam_tracker[key].append(ahora)
    spam_tracker[key] = [ts for ts in spam_tracker[key] if ahora - ts <= ventana]

    if len(spam_tracker[key]) >= limite:
        guild = message.guild
        miembro = message.author
        canal = message.channel

        spam_tracker[key].clear()

        # Borrar mensajes del spammer en todos los canales
        for canal_txt in guild.text_channels:
            try:
                msgs = [m async for m in canal_txt.history(limit=100) if m.author.id == user_id]
                if msgs:
                    await canal_txt.delete_messages(msgs)
            except Exception as e:
                logger.warning(f"No se pudieron borrar mensajes de spam en #{canal_txt.name}: {e}")

        # Slowmode progresivo en el canal donde se detectó
        nivel_actual = slowmode_tracker[canal.id]
        nuevo_nivel = min(nivel_actual + 1, len(SLOWMODE_NIVELES) - 1)
        slowmode_tracker[canal.id] = nuevo_nivel
        segundos_slowmode = SLOWMODE_NIVELES[nuevo_nivel]
        try:
            await canal.edit(slowmode_delay=segundos_slowmode)
        except Exception as e:
            logger.warning(f"No se pudo aplicar slowmode en #{canal.name}: {e}")

        embed = discord.Embed(
            title="🚨 Anti-Spam activado",
            description=f"**{miembro.mention}** envió spam en {canal.mention}.",
            color=COLORS["spam"]
        )
        embed.set_thumbnail(url=miembro.display_avatar.url)
        embed.add_field(name="👤 Usuario", value=f"`{miembro}` • ID: `{miembro.id}`", inline=True)
        embed.add_field(name="⏱️ Slowmode aplicado", value=f"`{segundos_slowmode}s` en {canal.mention}", inline=True)
        embed.set_footer(text="AegisBot • AutoMod", icon_url=bot.user.display_avatar.url if bot.user else None)
        embed.timestamp = discord.utils.utcnow()
        await enviar_log(guild, embed)

        # Aviso en el canal
        try:
            await canal.send(
                f"⚠️ **{miembro.mention}** fue detectado haciendo spam. Slowmode activado: **{segundos_slowmode}s**.",
                delete_after=10
            )
        except Exception:
            pass

        return True
    return False

# --- status dinámico (rota cada 30s) ---

_status_index = 0

@tasks.loop(seconds=30)
async def rotar_status():
    global _status_index
    total_miembros = sum(g.member_count for g in bot.guilds)
    total_servidores = len(bot.guilds)
    estados = [
        discord.Activity(type=discord.ActivityType.watching, name=f"{total_servidores} servidor{'es' if total_servidores != 1 else ''}"),
        discord.Activity(type=discord.ActivityType.watching, name=f"{total_miembros} miembros"),
        discord.Activity(type=discord.ActivityType.playing,  name="/ayuda"),
        discord.Activity(type=discord.ActivityType.watching, name="el servidor 🛡️"),
    ]
    await bot.change_presence(status=discord.Status.online, activity=estados[_status_index % len(estados)])
    _status_index += 1

@rotar_status.before_loop
async def before_rotar():
    await bot.wait_until_ready()

# borra entradas viejas de spam_tracker y raid_tracker cada 5 min para no acumular memoria

@tasks.loop(minutes=5)
async def limpiar_trackers():
    ahora = time.time()
    claves_spam = [k for k, v in list(spam_tracker.items()) if not v or (ahora - max(v)) > 300]
    for k in claves_spam:
        del spam_tracker[k]
    claves_raid = [k for k, v in list(raid_tracker.items()) if not v or (ahora - max(v)) > 300]
    for k in claves_raid:
        del raid_tracker[k]
    if claves_spam or claves_raid:
        logger.info(f"Trackers limpiados — spam: {len(claves_spam)} claves, raid: {len(claves_raid)} claves")

@limpiar_trackers.before_loop
async def before_limpiar():
    await bot.wait_until_ready()

# --- confirmación de ban ---

class BanConfirmView(ui.View):
    def __init__(self, miembro: discord.Member, razon: str, moderador: discord.Member):
        super().__init__(timeout=30)
        self.miembro = miembro
        self.razon = razon
        self.moderador = moderador
        self.ejecutado = False

    async def _limpiar(self, interaction: discord.Interaction):
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

    @ui.button(label="✅ Confirmar ban", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.moderador:
            await interaction.response.send_message("Solo el moderador que ejecutó el comando puede confirmar.", ephemeral=True)
            return
        self.ejecutado = True
        await self._limpiar(interaction)
        gid = self.miembro.guild.id
        try:
            await self.miembro.ban(reason=self.razon)
        except discord.Forbidden:
            await interaction.response.edit_message(
                content=f"❌ No tengo permisos para banear a **{self.miembro}**.", embed=None
            )
            return
        # Embed de confirmación
        embed = discord.Embed(
            title="🔨 Ban ejecutado",
            description=f"**{self.miembro}** fue baneado.",
            color=COLORS["ban"]
        )
        embed.set_thumbnail(url=self.miembro.display_avatar.url)
        embed.add_field(name="👤 Usuario", value=f"`{self.miembro}` • ID: `{self.miembro.id}`", inline=False)
        embed.add_field(name="🛡️ Moderador", value=self.moderador.mention, inline=True)
        embed.add_field(name="📝 Razón", value=self.razon, inline=True)
        embed.set_footer(text="AegisBot • Moderación", icon_url=bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.edit_message(content=None, embed=embed, view=self)
        # Log
        await enviar_log(self.miembro.guild, embed)

    @ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.moderador:
            await interaction.response.send_message("Solo el moderador que ejecutó el comando puede cancelar.", ephemeral=True)
            return
        self.ejecutado = True
        await self._limpiar(interaction)
        embed = discord.Embed(
            description=f"❌ Ban de **{self.miembro}** cancelado.",
            color=COLORS["adios"]
        )
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    async def on_timeout(self):
        if not self.ejecutado:
            for item in self.children:
                item.disabled = True

# --- eventos ---

@bot.event
async def on_ready():
    logger.info(f'Bot conectado como {bot.user}!')
    bot.add_view(TicketButtonView())
    bot.add_view(TicketCloseView())
    if not rotar_status.is_running():
        rotar_status.start()
    if not limpiar_trackers.is_running():
        limpiar_trackers.start()
    if not actualizar_giveaway_board.is_running():
        actualizar_giveaway_board.start()

    # Sync global
    try:
        synced = await bot.tree.sync()
        logger.info(f"Sync global completado — {len(synced)} comandos")
    except Exception as e:
        logger.error(f"Error en sync global: {e}")

@bot.event
async def on_guild_join(guild):
    # Comandos globales ya estan disponibles automaticamente.
    get_guild_config(guild.id)
    logger.info(f"Nuevo servidor: '{guild.name}' — config inicializada")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if not message.guild:
        return
    # admins no pasan por automod
    if message.author.guild_permissions.administrator:
        return

    cfg = get_guild_config(message.guild.id)

    # filtro de palabras — normalizado con unidecode para evitar evasión con acentos
    try:
        palabras_filtradas = cfg.get("filtro_palabras", [])
        if palabras_filtradas:
            contenido_norm = normalizar_texto(message.content)
            if any(normalizar_texto(p) in contenido_norm for p in palabras_filtradas):
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    await message.channel.send(t(message.guild.id, "filtro_detectado"), delete_after=5)
                except Exception:
                    pass
                return
    except Exception as e:
        logger.error(f"Error filtro palabras: {e}")

    # anti-links
    try:
        if cfg.get("anti_links", False) and URL_REGEX.search(message.content):
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.channel.send(t(message.guild.id, "antilink_detectado"), delete_after=5)
            except Exception:
                pass
            return
    except Exception as e:
        logger.error(f"Error anti-links: {e}")

    # anti-invites (separado de anti-links para poder activar uno sin el otro)
    try:
        if cfg.get("anti_invites", False) and INVITE_REGEX.search(message.content):
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.channel.send(t(message.guild.id, "antiinvite_detectado"), delete_after=5)
            except Exception:
                pass
            return
    except Exception as e:
        logger.error(f"Error anti-invites: {e}")

    # caps filter — mínimo 8 letras para no borrar "OK" o siglas cortas
    try:
        if cfg.get("caps_filter", False):
            letras = [c for c in message.content if c.isalpha()]
            if len(letras) >= 8:
                porcentaje_caps = sum(1 for c in letras if c.isupper()) / len(letras) * 100
                if porcentaje_caps >= cfg.get("caps_porcentaje", 70):
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    try:
                        await message.channel.send(t(message.guild.id, "caps_detectado"), delete_after=5)
                    except Exception:
                        pass
                    return
    except Exception as e:
        logger.error(f"Error caps filter: {e}")

    # emoji filter — usa emoji_lib si está disponible, sino el regex manual
    try:
        if cfg.get("emoji_filter", False):
            limite_emojis = cfg.get("emoji_limite", 10)
            if EMOJI_LIB_OK:
                emojis_unicode = len(emoji_lib.emoji_list(message.content))
            else:
                emojis_unicode = len(EMOJI_REGEX.findall(message.content))
            emojis_custom = len(re.findall(r"<a?:[a-zA-Z0-9_]+:[0-9]+>", message.content))
            if emojis_unicode + emojis_custom > limite_emojis:
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    await message.channel.send(t(message.guild.id, "emoji_detectado"), delete_after=5)
                except Exception:
                    pass
                return
    except Exception as e:
        logger.error(f"Error emoji filter: {e}")

    # anti-spam (va al final porque puede hacer kick, más costoso)
    try:
        if await verificar_spam(message):
            return
    except Exception as e:
        logger.error(f"Error anti-spam: {e}")

@bot.event
async def on_member_join(member):
    cfg = get_guild_config(member.guild.id)
    gid = member.guild.id

    # ── Anti-Raid ──────────────────────────────────────────────────
    try:
        if cfg.get("anti_raid", False):
            ahora = time.time()
            raid_tracker[gid].append(ahora)
            ventana = cfg.get("raid_segundos", 10)
            limite = cfg.get("raid_limite", 10)
            raid_tracker[gid] = [ts for ts in raid_tracker[gid] if ahora - ts <= ventana]

            if len(raid_tracker[gid]) >= limite:
                raid_tracker[gid].clear()
                # Lockdown: bloquear todos los canales de texto
                canales_bloqueados = 0
                rol_everyone = member.guild.default_role
                for canal in member.guild.text_channels:
                    try:
                        await canal.set_permissions(rol_everyone, send_messages=False)
                        canales_bloqueados += 1
                    except Exception:
                        pass
                # Alerta en canal de logs
                embed = discord.Embed(
                    title="🚨 RAID DETECTADO — LOCKDOWN ACTIVADO",
                    description=(
                        f"Se detectaron **{limite}+ joins** en **{ventana} segundos**.\n"
                        f"Se bloquearon **{canales_bloqueados} canales** automáticamente.\n\n"
                        f"Usa `/antiraid desactivar` para quitar el anti-raid y `/unlock` en cada canal cuando sea seguro."
                    ),
                    color=COLORS["raid"]
                )
                embed.add_field(name="⏱️ Ventana", value=f"`{ventana}` segundos", inline=True)
                embed.add_field(name="🔒 Canales bloqueados", value=f"`{canales_bloqueados}`", inline=True)
                embed.set_footer(text="AegisBot • Anti-Raid", icon_url=bot.user.display_avatar.url)
                embed.timestamp = discord.utils.utcnow()
                await enviar_log(member.guild, embed)
                # También avisar en general si no hay canal de logs
                canal_logs = cfg.get("canal_logs")
                if not canal_logs:
                    canal_general = discord.utils.get(member.guild.text_channels, name="general")
                    if canal_general:
                        try:
                            await canal_general.send(embed=embed)
                        except Exception:
                            pass
                return  # No enviar bienvenida durante un raid
    except Exception as e:
        logger.error(f"Error anti-raid: {e}")
    # ──────────────────────────────────────────────────────────────

    # ── Verificación de reportes globales ─────────────────────────
    try:
        reportes = get_reportes()
        uid = str(member.id)
        if uid in reportes:
            info = reportes[uid]
            embed_rep = discord.Embed(
                title=t(gid, "reporte_alerta_titulo"),
                description=t(gid, "reporte_alerta_desc", mencion=member.mention),
                color=COLORS["spam"]
            )
            embed_rep.set_thumbnail(url=member.display_avatar.url)
            embed_rep.add_field(name=f"📝 {t(gid, 'reporte_motivo_label')}", value=info.get("motivo", "?"), inline=False)
            embed_rep.add_field(name=f"🏠 {t(gid, 'reporte_en_servidor')}", value=info.get("servidor", "?"), inline=True)
            embed_rep.add_field(name="🪪 ID", value=f"`{member.id}`", inline=True)
            embed_rep.set_footer(text="AegisBot • Reportes Globales", icon_url=bot.user.display_avatar.url)
            embed_rep.timestamp = discord.utils.utcnow()
            await enviar_log(member.guild, embed_rep)
    except Exception as e:
        logger.error(f"Error verificando reportes en on_member_join: {e}")
    # ──────────────────────────────────────────────────────────────

    # ── Detección de cuenta nueva ──────────────────────────────────
    try:
        if cfg.get("cuenta_nueva", False):
            dias_minimos = cfg.get("cuenta_nueva_dias", 7)
            edad_cuenta = (discord.utils.utcnow() - member.created_at).days
            if edad_cuenta < dias_minimos:
                embed_alerta = discord.Embed(
                    title=t(gid, "cuenta_nueva_alerta_titulo"),
                    description=t(gid, "cuenta_nueva_alerta_desc", mencion=member.mention, dias=dias_minimos),
                    color=COLORS["spam"]
                )
                embed_alerta.set_thumbnail(url=member.display_avatar.url)
                embed_alerta.add_field(name="🆕 Edad de la cuenta", value=f"`{edad_cuenta}` días", inline=True)
                embed_alerta.add_field(name="📅 Cuenta creada", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
                embed_alerta.add_field(name="🪪 ID", value=f"`{member.id}`", inline=True)
                embed_alerta.set_footer(text="AegisBot • AutoMod", icon_url=bot.user.display_avatar.url)
                embed_alerta.timestamp = discord.utils.utcnow()
                await enviar_log(member.guild, embed_alerta)
    except Exception as e:
        logger.error(f"Error detección cuenta nueva: {e}")
    # ──────────────────────────────────────────────────────────────

    canal_id = cfg.get("canal_bienvenida")
    if canal_id:
        canal = member.guild.get_channel(int(canal_id))
    else:
        # Buscar #general, #bienvenida, #welcome o el primer canal de texto
        canal = (
            discord.utils.get(member.guild.text_channels, name="general")
            or discord.utils.get(member.guild.text_channels, name="bienvenida")
            or discord.utils.get(member.guild.text_channels, name="welcome")
            or (member.guild.text_channels[0] if member.guild.text_channels else None)
        )

    if not canal:
        logger.warning(f"on_member_join: no se encontró canal para bienvenida en {member.guild.name}")
        return

    if canal:
        miembros = member.guild.member_count
        # Embed de bienvenida (siempre se envía)
        embed = discord.Embed(
            title=f"✨ {t(gid, 'bienvenida_msg', usuario=member.name)}",
            description=(
                f"{t(gid, 'bienvenida_desc', mencion=member.mention)}\n\n"
                f"📅 Cuenta creada: <t:{int(member.created_at.timestamp())}:R>\n"
                f"👥 Eres el miembro número **{miembros}**"
            ),
            color=COLORS["bienvenida"]
        )
        embed.set_footer(text=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
        embed.timestamp = discord.utils.utcnow()

        tarjeta = await generar_tarjeta_bienvenida(member)
        try:
            if tarjeta:
                # Solo la imagen, sin embed encima
                await canal.send(file=tarjeta)
            else:
                embed.set_thumbnail(url=member.display_avatar.url)
                await canal.send(embed=embed)
        except Exception as e:
            logger.warning(f"Error enviando bienvenida a {member}: {e}")

@bot.event
async def on_member_remove(member):
    cfg = get_guild_config(member.guild.id)
    gid = member.guild.id
    canal_id = cfg.get("canal_bienvenida")
    if canal_id:
        canal = member.guild.get_channel(int(canal_id))
    else:
        canal = (
            discord.utils.get(member.guild.text_channels, name="general")
            or discord.utils.get(member.guild.text_channels, name="bienvenida")
            or discord.utils.get(member.guild.text_channels, name="welcome")
            or (member.guild.text_channels[0] if member.guild.text_channels else None)
        )

    if not canal:
        logger.warning(f"on_member_remove: no se encontró canal en {member.guild.name}")
        return

    if member.joined_at:
        tiempo = f"<t:{int(member.joined_at.timestamp())}:R>"
    else:
        tiempo = "Desconocido"
    embed = discord.Embed(
        title="👋 Hasta luego",
        description=f"**{member.name}** ha salido del servidor.\n📅 Estuvo con nosotros desde {tiempo}",
        color=COLORS["adios"]
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
    embed.timestamp = discord.utils.utcnow()
    try:
        await canal.send(embed=embed)
    except Exception as e:
        logger.warning(f"Error enviando despedida de {member}: {e}")

@bot.event
async def on_message_delete(message):
    if not message.guild or message.author.bot:
        return
    contenido = message.content or "[sin contenido de texto]"
    log_mensaje_archivo(
        tipo="eliminado",
        guild_id=message.guild.id,
        guild_name=message.guild.name,
        canal_name=message.channel.name,
        usuario=str(message.author),
        usuario_id=message.author.id,
        contenido_antes=contenido
    )

@bot.event
async def on_message_edit(before, after):
    if not before.guild or before.author.bot:
        return
    if before.content == after.content:
        return
    log_mensaje_archivo(
        tipo="editado",
        guild_id=before.guild.id,
        guild_name=before.guild.name,
        canal_name=before.channel.name,
        usuario=str(before.author),
        usuario_id=before.author.id,
        contenido_antes=before.content or "[vacío]",
        contenido_despues=after.content or "[vacío]"
    )

# Handler de errores para comandos slash
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logger.error(f"Error slash [{interaction.command.name if interaction.command else '?'}]: {error}")
    # Mensajes fijos sin llamar a t() para evitar errores en cascada
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ No tienes permisos para usar este comando."
    elif isinstance(error, app_commands.BotMissingPermissions):
        msg = "❌ No tengo los permisos necesarios para hacer eso."
    elif isinstance(error, app_commands.CommandOnCooldown):
        msg = f"⏳ Espera {error.retry_after:.1f} segundos."
    else:
        msg = f"❌ Error: {type(error).__name__}"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error(f"Error en handler de errores: {e}")

# --- comandos slash ---

@bot.tree.command(name='sync', description='Fuerza la sincronización de comandos (solo admins).')
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Solo administradores.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        bot.tree.copy_global_to(guild=interaction.guild)
        synced = await bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(f"✅ Sincronizados {len(synced)} comandos en este servidor.", ephemeral=True)
        logger.info(f"Sync manual: {len(synced)} comandos en {interaction.guild.name}")
    except Exception as e:
        await interaction.followup.send(f"❌ Error al sincronizar: {e}", ephemeral=True)

@bot.tree.command(name='config', description='Panel de configuración del bot (solo admins).')
async def config_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t(interaction.guild.id, "solo_admin"), ephemeral=True)
        return
    # Responder inmediatamente para no expirar la interacción (3s limit)
    await interaction.response.defer(ephemeral=True)
    try:
        view = ConfigView(interaction.guild, authorized_user_id=interaction.user.id)
        panel = await interaction.followup.send(
            embed=build_panel_embed(interaction.guild),
            view=view,
            ephemeral=True,
            wait=True
        )
        view.panel_message = panel
    except discord.NotFound:
        logger.warning("config: interaccion expirada (10062), el usuario tardó demasiado o la red es lenta.")
    except Exception as e:
        logger.error(f"config: error inesperado — {e}")
        try:
            await interaction.followup.send("❌ Error al abrir el panel. Intenta de nuevo.", ephemeral=True)
        except Exception:
            pass

@bot.tree.command(name='ping', description='Muestra la latencia del bot.')
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f'Pong! {round(bot.latency * 1000)}ms')

@bot.tree.command(name='limpiar', description='Elimina mensajes del canal (1 a 500).')
@app_commands.describe(cantidad='Cantidad de mensajes a eliminar (máximo 500)')
async def limpiar(interaction: discord.Interaction, cantidad: int):
    cfg = get_guild_config(interaction.guild.id)
    gid = interaction.guild.id
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
        return
    if cantidad < 1 or cantidad > 500:
        await interaction.response.send_message("La cantidad debe estar entre 1 y 500.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    eliminados = 0

    try:
        # Bulk delete (mensajes < 14 días, rápido)
        deleted = await interaction.channel.purge(limit=cantidad)
        eliminados = len(deleted)
    except discord.Forbidden:
        await interaction.followup.send(t(gid, "sin_permisos_bot"), ephemeral=True)
        return
    except Exception:
        # Fallback uno por uno (mensajes más antiguos)
        async for msg in interaction.channel.history(limit=cantidad):
            try:
                await msg.delete()
                eliminados += 1
            except Exception:
                pass

    await interaction.followup.send(t(gid, "borrados", n=eliminados), ephemeral=True)

@bot.tree.command(name='kick', description='Expulsa a un miembro del servidor.')
@app_commands.describe(miembro='Miembro a expulsar', razon='Razón de la expulsión')
async def kick(interaction: discord.Interaction, miembro: discord.Member, razon: str = "Sin razón"):
    cfg = get_guild_config(interaction.guild.id)
    gid = interaction.guild.id
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
        return
    if miembro.top_role >= interaction.guild.me.top_role:
        await interaction.response.send_message(t(gid, "sin_permisos_bot"), ephemeral=True)
        return
    await interaction.response.defer()
    try:
        await miembro.kick(reason=razon)
    except discord.Forbidden:
        await interaction.followup.send(t(gid, "sin_permisos_bot"), ephemeral=True)
        return
    except Exception as e:
        logger.error(f"Error al expulsar a {miembro}: {e}")
        await interaction.followup.send("❌ Ocurrió un error al expulsar al usuario.", ephemeral=True)
        return
    await interaction.followup.send(t(gid, "expulsado", usuario=miembro.name, razon=razon))
    embed = discord.Embed(
        title="👢 Miembro expulsado",
        description=f"**{miembro.mention}** fue expulsado del servidor.",
        color=COLORS["kick"]
    )
    embed.set_thumbnail(url=miembro.display_avatar.url)
    embed.add_field(name="👤 Usuario", value=f"{miembro.mention}\n`{miembro}` • ID: `{miembro.id}`", inline=False)
    embed.add_field(name="🛡️ Moderador", value=f"{interaction.user.mention}", inline=True)
    embed.add_field(name="📝 Razón", value=razon, inline=True)
    embed.set_footer(text=f"AegisBot • Moderación", icon_url=bot.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    await enviar_log(interaction.guild, embed)

@bot.tree.command(name='ban', description='Banea a un miembro del servidor (pide confirmación).')
@app_commands.describe(miembro='Miembro a banear', razon='Razón del ban')
async def ban(interaction: discord.Interaction, miembro: discord.Member, razon: str = "Sin razón"):
    cfg = get_guild_config(interaction.guild.id)
    gid = interaction.guild.id
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
        return
    if miembro.top_role >= interaction.guild.me.top_role:
        await interaction.response.send_message(t(gid, "sin_permisos_bot"), ephemeral=True)
        return
    if miembro == interaction.user:
        await interaction.response.send_message("❌ No puedes banearte a ti mismo.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(
        title="⚠️ Confirmar ban",
        description=(
            f"¿Seguro que quieres banear a **{miembro.mention}**?\n"
            f"Esta acción **no se puede deshacer** fácilmente."
        ),
        color=COLORS["ban"]
    )
    embed.set_thumbnail(url=miembro.display_avatar.url)
    embed.add_field(name="👤 Usuario", value=f"`{miembro}` • ID: `{miembro.id}`", inline=False)
    embed.add_field(name="📝 Razón", value=razon, inline=False)
    embed.set_footer(text="⏳ Esta confirmación expira en 30 segundos.", icon_url=bot.user.display_avatar.url)
    view = BanConfirmView(miembro=miembro, razon=razon, moderador=interaction.user)
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name='unban', description='Desbanea a un usuario por su nombre (usuario#0000).')
@app_commands.describe(nombre='Nombre del usuario baneado, ej: usuario#1234')
async def unban(interaction: discord.Interaction, nombre: str):
    cfg = get_guild_config(interaction.guild.id)
    gid = interaction.guild.id
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
        return
    await interaction.response.defer()
    bans = [entry async for entry in interaction.guild.bans()]
    for ban_entry in bans:
        user = ban_entry.user
        if str(user) == nombre or user.name == nombre:
            await interaction.guild.unban(user)
            await interaction.followup.send(t(gid, "desbaneado", usuario=user.name))
            embed = discord.Embed(
                title="✅ Ban removido",
                description=f"**{user.mention if hasattr(user, 'mention') else user.name}** fue desbaneado del servidor.",
                color=COLORS["unban"]
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="👤 Usuario", value=f"`{user}` • ID: `{user.id}`", inline=False)
            embed.add_field(name="🛡️ Moderador", value=f"{interaction.user.mention}", inline=True)
            embed.set_footer(text="AegisBot • Moderación", icon_url=bot.user.display_avatar.url)
            embed.timestamp = discord.utils.utcnow()
            await enviar_log(interaction.guild, embed)
            return
    await interaction.followup.send(t(gid, "no_baneado"))

@bot.tree.command(name='mute', description='Silencia a un miembro del servidor.')
@app_commands.describe(miembro='Miembro a silenciar')
async def mute(interaction: discord.Interaction, miembro: discord.Member):
    cfg = get_guild_config(interaction.guild.id)
    gid = interaction.guild.id
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
        return
    if miembro.top_role >= interaction.guild.me.top_role:
        await interaction.response.send_message(t(gid, "sin_permisos_bot"), ephemeral=True)
        return
    await interaction.response.defer()
    rol_mute = await obtener_o_crear_rol_muted(interaction.guild)
    if not rol_mute:
        await interaction.followup.send(t(gid, "sin_permisos_bot"))
        return
    await miembro.add_roles(rol_mute)
    await interaction.followup.send(t(gid, "silenciado", usuario=miembro.name))
    embed = discord.Embed(
        title="🔇 Miembro silenciado",
        description=f"**{miembro.mention}** no puede enviar mensajes.",
        color=COLORS["mute"]
    )
    embed.set_thumbnail(url=miembro.display_avatar.url)
    embed.add_field(name="👤 Usuario", value=f"{miembro.mention}\n`{miembro}` • ID: `{miembro.id}`", inline=False)
    embed.add_field(name="🛡️ Moderador", value=f"{interaction.user.mention}", inline=True)
    embed.set_footer(text="AegisBot • Moderación", icon_url=bot.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    await enviar_log(interaction.guild, embed)

@bot.tree.command(name='unmute', description='Quita el silencio a un miembro.')
@app_commands.describe(miembro='Miembro a des-silenciar')
async def unmute(interaction: discord.Interaction, miembro: discord.Member):
    cfg = get_guild_config(interaction.guild.id)
    gid = interaction.guild.id
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
        return
    rol_mute = discord.utils.get(interaction.guild.roles, name="Muted")
    if rol_mute and rol_mute in miembro.roles:
        await interaction.response.defer()
        await miembro.remove_roles(rol_mute)
        await interaction.followup.send(t(gid, "dessilenciado", usuario=miembro.name))
        embed = discord.Embed(
            title="🔊 Miembro des-silenciado",
            description=f"**{miembro.mention}** puede volver a enviar mensajes.",
            color=COLORS["unmute"]
        )
        embed.set_thumbnail(url=miembro.display_avatar.url)
        embed.add_field(name="👤 Usuario", value=f"{miembro.mention}\n`{miembro}` • ID: `{miembro.id}`", inline=False)
        embed.add_field(name="🛡️ Moderador", value=f"{interaction.user.mention}", inline=True)
        embed.set_footer(text="AegisBot • Moderación", icon_url=bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await enviar_log(interaction.guild, embed)
    else:
        await interaction.response.send_message(t(gid, "no_silenciado", usuario=miembro.name), ephemeral=True)

@bot.tree.command(name='filtro', description='Gestiona el filtro de palabras prohibidas.')
@app_commands.describe(
    accion='Acción a realizar',
    palabra='Palabra a agregar o quitar del filtro'
)
@app_commands.choices(accion=[
    app_commands.Choice(name='Agregar palabra', value='add'),
    app_commands.Choice(name='Quitar palabra', value='remove'),
    app_commands.Choice(name='Ver lista', value='list'),
])
async def filtro(interaction: discord.Interaction, accion: app_commands.Choice[str], palabra: str = None):
    cfg = get_guild_config(interaction.guild.id)
    gid = interaction.guild.id
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    if accion.value == 'add':
        if not palabra:
            await interaction.followup.send("Debes escribir una palabra.", ephemeral=True)
            return
        palabra = palabra.lower().strip()
        if palabra not in cfg["filtro_palabras"]:
            cfg["filtro_palabras"].append(palabra)
            await guardar_config_async()
            await interaction.followup.send(t(gid, "filtro_agregado", palabra=palabra), ephemeral=True)
        else:
            await interaction.followup.send(t(gid, "filtro_ya_existe"), ephemeral=True)

    elif accion.value == 'remove':
        if not palabra:
            await interaction.followup.send("Debes escribir una palabra.", ephemeral=True)
            return
        palabra = palabra.lower().strip()
        if palabra in cfg["filtro_palabras"]:
            cfg["filtro_palabras"].remove(palabra)
            await guardar_config_async()
            await interaction.followup.send(t(gid, "filtro_quitado", palabra=palabra), ephemeral=True)
        else:
            await interaction.followup.send(t(gid, "filtro_no_existe"), ephemeral=True)

    elif accion.value == 'list':
        lista = cfg.get("filtro_palabras", [])
        if lista:
            await interaction.followup.send(
                t(gid, "filtro_lista", lista=", ".join(f"`{p}`" for p in lista)), ephemeral=True
            )
        else:
            await interaction.followup.send(t(gid, "filtro_vacio"), ephemeral=True)

@bot.tree.command(name='antilink', description='Activa o desactiva el bloqueo de links en el servidor.')
@app_commands.describe(estado='Activar o desactivar el anti-links')
@app_commands.choices(estado=[
    app_commands.Choice(name='Activar', value='on'),
    app_commands.Choice(name='Desactivar', value='off'),
])
async def antilink(interaction: discord.Interaction, estado: app_commands.Choice[str]):
    cfg = get_guild_config(interaction.guild.id)
    gid = interaction.guild.id
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    cfg["anti_links"] = (estado.value == "on")
    await guardar_config_async()
    clave = "antilink_on" if estado.value == "on" else "antilink_off"
    await interaction.followup.send(t(gid, clave), ephemeral=True)

@bot.tree.command(name='ayuda', description='Muestra todos los comandos disponibles / Shows all available commands.')
async def ayuda(interaction: discord.Interaction):
    await interaction.response.defer()
    gid = interaction.guild.id if interaction.guild else 0
    idioma = get_guild_config(gid).get("idioma", "es") if interaction.guild else "es"

    if idioma == "en":
        embed = discord.Embed(
            title="📖 AegisBot — Commands",
            description="All commands use `/`. Moderation commands require a mod role or administrator.",
            color=COLORS["ayuda"]
        )
        embed.add_field(name="⚙️ Administration", value=(
            "`/config` — Opens the bot configuration panel. Set mod roles, log channel, welcome channel, anti-spam, language, word filter, anti-links, anti-raid and more.\n"
            "`/sync` — Forces a slash command sync for this server. Use it if commands don't appear."
        ), inline=False)
        embed.add_field(name="🔨 Moderation", value=(
            "`/kick @user [reason]` — Kicks a user from the server.\n"
            "`/ban @user [reason]` — Bans a user. Asks for confirmation before executing.\n"
            "`/unban username#0000` — Unbans a previously banned user.\n"
            "`/mute @user` — Mutes a user (creates a Muted role automatically if needed).\n"
            "`/unmute @user` — Removes the mute from a user.\n"
            "`/limpiar [amount]` — Deletes 1 to 500 messages from the current channel.\n"
            "`/lock [reason]` — Locks the current channel so regular users can't send messages.\n"
            "`/unlock [reason]` — Unlocks the current channel."
        ), inline=False)
        embed.add_field(name="🛡️ AutoMod", value=(
            "`/filtro add/remove/list [word]` — Manages the word filter. Filtered messages are deleted automatically.\n"
            "`/antilink on/off` — Blocks all links in the server.\n"
            "`/antiraid on/off [joins] [seconds]` — Locks all channels automatically if too many users join in a short time.\n"
            "Anti-Invites, Caps Filter, Emoji Filter, New Account alert → configured via `/config`."
        ), inline=False)
        embed.add_field(name="🚨 Global Reports", value=(
            "`/reportar @user reason` — Flags a user globally. All servers with AegisBot get an alert when that user joins.\n"
            "`/quitar_reporte @user` — Removes the global flag from a user.\n"
            "`/reportes` — Shows the full list of globally flagged users."
        ), inline=False)
        embed.add_field(name="🎨 Utility", value=(
            "`/embed title description [color] [image] [footer]` — Posts a custom embed announcement in the current channel.\n"
            "`/tickets` — Opens the ticket system setup panel. Configure channel, category, logs and support role."
        ), inline=False)
        embed.add_field(name="🌍 APIs", value=(
            "`/clima city` — Shows current weather for any city.\n"
            "`/giveaway [platform]` — Shows active free game giveaways. Can filter by platform."
        ), inline=False)
        embed.add_field(name="ℹ️ Information", value=(
            "`/ping` — Shows the bot's current latency.\n"
            "`/info` — Shows server information: members, channels, roles, creation date.\n"
            "`/usuario [@user]` — Shows a user's profile: ID, roles, join date, account age."
        ), inline=False)
    else:
        embed = discord.Embed(
            title="📖 AegisBot — Comandos",
            description="Todos los comandos usan `/`. Los de moderación requieren rol moderador o administrador.",
            color=COLORS["ayuda"]
        )
        embed.add_field(name="⚙️ Administración", value=(
            "`/config` — Abre el panel de configuración del bot. Configura roles mod, canal de logs, bienvenida, anti-spam, idioma, filtro de palabras, anti-links, anti-raid y más.\n"
            "`/sync` — Fuerza una sincronización de los comandos slash en este servidor. Úsalo si los comandos no aparecen."
        ), inline=False)
        embed.add_field(name="🔨 Moderación", value=(
            "`/kick @usuario [razón]` — Expulsa a un usuario del servidor.\n"
            "`/ban @usuario [razón]` — Banea a un usuario. Pide confirmación antes de ejecutar.\n"
            "`/unban usuario#0000` — Desbanea a un usuario previamente baneado.\n"
            "`/mute @usuario` — Silencia a un usuario (crea el rol Muted automáticamente si no existe).\n"
            "`/unmute @usuario` — Quita el silencio a un usuario.\n"
            "`/limpiar [cantidad]` — Elimina entre 1 y 500 mensajes del canal actual.\n"
            "`/lock [razón]` — Bloquea el canal actual para que los usuarios normales no puedan escribir.\n"
            "`/unlock [razón]` — Desbloquea el canal actual."
        ), inline=False)
        embed.add_field(name="🛡️ AutoMod", value=(
            "`/filtro agregar/quitar/ver [palabra]` — Gestiona el filtro de palabras. Los mensajes con palabras prohibidas se eliminan automáticamente.\n"
            "`/antilink on/off` — Bloquea todos los enlaces en el servidor.\n"
            "`/antiraid on/off [joins] [segundos]` — Bloquea todos los canales automáticamente si entran demasiados usuarios en poco tiempo.\n"
            "Anti-Invites, Filtro de Mayúsculas, Filtro de Emojis, Alerta de Cuenta Nueva → se configuran desde `/config`."
        ), inline=False)
        embed.add_field(name="🚨 Reportes Globales", value=(
            "`/reportar @usuario motivo` — Marca a un usuario globalmente. Todos los servidores con AegisBot reciben una alerta cuando esa persona se une.\n"
            "`/quitar_reporte @usuario` — Elimina la marca global de un usuario.\n"
            "`/reportes` — Muestra la lista completa de usuarios marcados globalmente."
        ), inline=False)
        embed.add_field(name="🎨 Utilidad", value=(
            "`/embed título descripción [color] [imagen] [pie]` — Publica un embed personalizado como anuncio en el canal actual.\n"
            "`/tickets` — Abre el panel de configuración del sistema de tickets. Configura canal, categoría, logs y rol de soporte."
        ), inline=False)
        embed.add_field(name="🌍 APIs", value=(
            "`/clima ciudad` — Muestra el clima actual de cualquier ciudad.\n"
            "`/giveaway [plataforma]` — Muestra giveaways de juegos gratuitos activos ahora mismo. Se puede filtrar por plataforma."
        ), inline=False)
        embed.add_field(name="ℹ️ Información", value=(
            "`/ping` — Muestra la latencia actual del bot.\n"
            "`/info` — Muestra información del servidor: miembros, canales, roles, fecha de creación.\n"
            "`/usuario [@usuario]` — Muestra el perfil de un usuario: ID, roles, fecha de entrada, antigüedad de la cuenta."
        ), inline=False)

    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.set_footer(text="AegisBot • by Anthonydev", icon_url=bot.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)

@bot.tree.command(name='lock', description='Bloquea el canal actual para que usuarios no puedan escribir.')
@app_commands.describe(razon='Razón del bloqueo (opcional)')
async def lock(interaction: discord.Interaction, razon: str = "Sin razón"):
    cfg = get_guild_config(interaction.guild.id)
    gid = interaction.guild.id
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
        return
    canal = interaction.channel
    rol_everyone = interaction.guild.default_role
    await interaction.response.defer()
    try:
        await canal.set_permissions(rol_everyone, send_messages=False)
        embed = discord.Embed(
            title="🔒 Canal bloqueado",
            description=(
                f"**{canal.mention}** fue bloqueado.\n"
                f"👮 Moderador: {interaction.user.mention}\n"
                f"📝 Razón: {razon}"
            ),
            color=COLORS["lock"]
        )
        embed.set_footer(text="AegisBot • Moderación", icon_url=bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)
        log_embed = discord.Embed(
            title="🔒 Canal bloqueado",
            description=f"Canal {canal.mention} bloqueado por {interaction.user.mention}.",
            color=COLORS["lock"]
        )
        log_embed.add_field(name="📋 Canal", value=canal.mention, inline=True)
        log_embed.add_field(name=f"🛡️ {t(gid, 'moderador_field')}", value=str(interaction.user), inline=True)
        log_embed.add_field(name=f"📝 {t(gid, 'razon_field')}", value=razon, inline=False)
        log_embed.set_footer(text="AegisBot • Moderación", icon_url=bot.user.display_avatar.url)
        log_embed.timestamp = discord.utils.utcnow()
        await enviar_log(interaction.guild, log_embed)
    except discord.Forbidden:
        await interaction.followup.send(t(gid, "sin_permisos_bot"), ephemeral=True)

@bot.tree.command(name='unlock', description='Desbloquea el canal actual para que usuarios puedan escribir.')
@app_commands.describe(razon='Razón del desbloqueo (opcional)')
async def unlock(interaction: discord.Interaction, razon: str = "Sin razón"):
    cfg = get_guild_config(interaction.guild.id)
    gid = interaction.guild.id
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
        return
    canal = interaction.channel
    rol_everyone = interaction.guild.default_role
    await interaction.response.defer()
    try:
        await canal.set_permissions(rol_everyone, send_messages=None)
        embed = discord.Embed(
            title="🔓 Canal desbloqueado",
            description=(
                f"**{canal.mention}** vuelve a estar abierto.\n"
                f"👮 Moderador: {interaction.user.mention}\n"
                f"📝 Razón: {razon}"
            ),
            color=COLORS["unlock"]
        )
        embed.set_footer(text="AegisBot • Moderación", icon_url=bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)
        log_embed = discord.Embed(
            title="🔓 Canal desbloqueado",
            description=f"Canal {canal.mention} desbloqueado por {interaction.user.mention}.",
            color=COLORS["unlock"]
        )
        log_embed.add_field(name="📋 Canal", value=canal.mention, inline=True)
        log_embed.add_field(name=f"🛡️ {t(gid, 'moderador_field')}", value=str(interaction.user), inline=True)
        log_embed.add_field(name=f"📝 {t(gid, 'razon_field')}", value=razon, inline=False)
        log_embed.set_footer(text="AegisBot • Moderación", icon_url=bot.user.display_avatar.url)
        log_embed.timestamp = discord.utils.utcnow()
        await enviar_log(interaction.guild, log_embed)
    except discord.Forbidden:
        await interaction.followup.send(t(gid, "sin_permisos_bot"), ephemeral=True)

@bot.tree.command(name='embed', description='Publica un anuncio con embed en el canal actual.')
@app_commands.describe(
    titulo='Título del embed',
    descripcion='Contenido del embed',
    color='Color en hexadecimal, ej: ff0000 (rojo), 00ff00 (verde), 0000ff (azul)',
    imagen='URL de una imagen para mostrar (opcional)',
    pie='Texto pequeño al pie del embed (opcional)'
)
async def embed_cmd(interaction: discord.Interaction,
                    titulo: str,
                    descripcion: str,
                    color: str = "5865f2",
                    imagen: str = None,
                    pie: str = None):
    cfg = get_guild_config(interaction.guild.id)
    gid = interaction.guild.id
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
        return

    # Parsear color
    try:
        color_int = int(color.strip("#"), 16)
    except ValueError:
        await interaction.response.send_message(
            "❌ Color inválido. Usa formato hex sin #, ej: `ff0000`", ephemeral=True
        )
        return

    embed = discord.Embed(
        title=titulo,
        description=descripcion,
        color=color_int
    )
    if imagen:
        embed.set_image(url=imagen)
    if pie:
        embed.set_footer(text=pie)
    embed.timestamp = discord.utils.utcnow()

    await interaction.response.defer(ephemeral=True)
    await interaction.channel.send(embed=embed)
    await interaction.followup.send("✅ Embed publicado.", ephemeral=True)

@bot.tree.command(name='info', description='Información del servidor.')
async def info(interaction: discord.Interaction):
    await interaction.response.defer()
    guild = interaction.guild
    embed = discord.Embed(
        title=f"📊 {guild.name}",
        description=guild.description or "Sin descripción.",
        color=COLORS["info"]
    )
    embed.add_field(name="👑 Dueño", value=f"<@{guild.owner_id}>", inline=True)
    embed.add_field(name="👥 Miembros", value=f"`{guild.member_count}`", inline=True)
    embed.add_field(name="💬 Canales", value=f"`{len(guild.text_channels)}` texto · `{len(guild.voice_channels)}` voz", inline=True)
    embed.add_field(name="🎭 Roles", value=f"`{len(guild.roles)}`", inline=True)
    embed.add_field(name="😀 Emojis", value=f"`{len(guild.emojis)}`", inline=True)
    embed.add_field(name="📅 Creado", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    if guild.banner:
        embed.set_image(url=guild.banner.url)
    embed.set_footer(text=f"ID del servidor: {guild.id} • AegisBot", icon_url=guild.icon.url if guild.icon else None)
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)

@bot.tree.command(name='usuario', description='Información de un usuario.')
@app_commands.describe(miembro='Usuario a consultar (opcional, por defecto tú mismo)')
async def usuario(interaction: discord.Interaction, miembro: discord.Member = None):
    await interaction.response.defer()
    miembro = miembro or interaction.user
    roles = [r.mention for r in reversed(miembro.roles) if r.name != "@everyone"]
    embed = discord.Embed(
        title=f"👤 {miembro.display_name}",
        description=f"`{miembro}` • {'🤖 Bot' if miembro.bot else '👥 Usuario'}",
        color=miembro.color if miembro.color.value != 0 else COLORS["info"]
    )
    embed.set_thumbnail(url=miembro.display_avatar.url)
    embed.add_field(name="🪪 ID", value=f"`{miembro.id}`", inline=True)
    joined_str = f"<t:{int(miembro.joined_at.timestamp())}:R>" if miembro.joined_at else "Desconocido"
    embed.add_field(name="📅 En el servidor", value=joined_str, inline=True)
    embed.add_field(name="🗓️ Cuenta creada", value=f"<t:{int(miembro.created_at.timestamp())}:R>", inline=True)
    if roles:
        roles_text = " ".join(roles[:10])
        if len(roles) > 10:
            roles_text += f" y {len(roles) - 10} más..."
        embed.add_field(name=f"🎭 Roles ({len(roles)})", value=roles_text, inline=False)
    embed.set_footer(text=f"Solicitado por {interaction.user}", icon_url=interaction.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)

@bot.tree.command(name='antiraid', description='Activa o desactiva el anti-raid y configura sus parámetros.')
@app_commands.describe(
    estado='Activar o desactivar',
    limite='Cantidad de joins para disparar el raid (default: 10)',
    segundos='Ventana de tiempo en segundos (default: 10)'
)
@app_commands.choices(estado=[
    app_commands.Choice(name='Activar', value='on'),
    app_commands.Choice(name='Desactivar', value='off'),
])
async def antiraid(interaction: discord.Interaction,
                   estado: app_commands.Choice[str],
                   limite: int = 10,
                   segundos: int = 10):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t(interaction.guild.id, "solo_admin"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    cfg = get_guild_config(interaction.guild.id)
    cfg["anti_raid"] = (estado.value == "on")
    cfg["raid_limite"] = max(3, limite)
    cfg["raid_segundos"] = max(3, segundos)
    await guardar_config_async()

    if estado.value == "on":
        embed = discord.Embed(
            title="🛡️ Anti-Raid activado",
            description=f"Se bloqueará el servidor si entran **{cfg['raid_limite']}+ miembros** en **{cfg['raid_segundos']} segundos**.",
            color=COLORS["ok"]
        )
    else:
        embed = discord.Embed(
            title="🛡️ Anti-Raid desactivado",
            description="El servidor ya no tiene protección anti-raid activa.",
            color=COLORS["adios"]
        )
    embed.set_footer(text="AegisBot • Anti-Raid", icon_url=bot.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed, ephemeral=True)

# --- giveaway board ---
# Task cada 15 min: edita el mensaje fijo en el canal configurado.
# Si el mensaje fue borrado, manda uno nuevo y guarda el ID.

def build_giveaway_board_embed(gid: int, data: list) -> discord.Embed:
    if not data:
        embed = discord.Embed(
            title="🎮 Giveaways — Sin resultados",
            description=t(gid, "giveaway_board_vacio"),
            color=COLORS["giveaway"]
        )
        embed.set_footer(text="AegisBot • Giveaways · gamerpower.com", icon_url=bot.user.display_avatar.url if bot.user else None)
        embed.timestamp = discord.utils.utcnow()
        return embed

    giveaways = data[:5]
    embed = discord.Embed(
        title="🎮 Giveaways activos ahora",
        description=t(gid, "giveaway_board_desc"),
        color=COLORS["giveaway"]
    )
    if giveaways[0].get("thumbnail"):
        embed.set_thumbnail(url=giveaways[0]["thumbnail"])

    for g in giveaways:
        titulo   = g.get("title", "Sin título")[:80]
        worth    = g.get("worth", "N/A")
        plats    = g.get("platforms", "N/A")
        end_date = g.get("end_date", "")
        users    = g.get("users", 0)
        link     = g.get("open_giveaway_url", g.get("open_giveaway", "https://www.gamerpower.com"))
        tipo     = g.get("type", "")

        if end_date and end_date.upper() != "N/A":
            try:
                dt = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                expira_str = f"<t:{int(dt.timestamp())}:R>"
            except ValueError:
                expira_str = end_date
        else:
            expira_str = t(gid, "giveaway_sin_fecha")

        badge = "🎮" if tipo.lower() == "game" else "🎁"
        valor_field = (
            f"{badge} **[{titulo}]({link})**\n"
            f"💰 Valor: `{worth}` · 👥 `{users:,}` {t(gid, 'giveaway_usuarios')}\n"
            f"🖥️ {plats}\n"
            f"⏳ {t(gid, 'giveaway_expira')}: {expira_str}"
        )
        embed.add_field(name="\u200b", value=valor_field, inline=False)

    embed.set_footer(
        text="AegisBot • Giveaways · gamerpower.com · actualizado",
        icon_url=bot.user.display_avatar.url if bot.user else None
    )
    embed.timestamp = discord.utils.utcnow()
    return embed


@tasks.loop(minutes=15)
async def actualizar_giveaway_board():
    """Actualiza el tablero de giveaways en todos los servidores que lo tienen configurado."""
    # Fetch único a la API para todos los guilds (no repetir por cada uno)
    data = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://www.gamerpower.com/api/giveaways?sort-by=popularity",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    raw = await resp.json(content_type=None)
                    if isinstance(raw, list):
                        data = raw
    except Exception as e:
        logger.warning(f"Giveaway board: error al obtener datos de API — {e}")
        return  # Si la API falla, no editar nada

    # Iterar todos los guilds configurados
    for gid_str, cfg in list(server_config.items()):
        canal_id = cfg.get("giveaway_canal")
        if not canal_id:
            continue

        try:
            guild = bot.get_guild(int(gid_str))
            if not guild:
                continue
            canal = guild.get_channel(int(canal_id))
            if not canal:
                continue

            gid = int(gid_str)
            embed = build_giveaway_board_embed(gid, data)

            msg_id = cfg.get("giveaway_message_id")
            if msg_id:
                # Intentar editar el mensaje existente
                msg = None
                try:
                    msg = await canal.fetch_message(int(msg_id))
                    await msg.edit(embed=embed)
                    continue  # Editado OK, pasar al siguiente guild
                except discord.NotFound:
                    # El mensaje fue borrado, caer al envío nuevo
                    logger.info(f"Giveaway board: mensaje {msg_id} no encontrado en {guild.name}, enviando nuevo.")
                    cfg["giveaway_message_id"] = None
                    await guardar_config_async()
                except discord.Forbidden:
                    logger.warning(f"Giveaway board: sin permisos para editar en {guild.name}")
                    continue
                except discord.HTTPException as e:
                    if e.status == 400:
                        # Mensaje incompatible (ej. Components V2) → borrar y enviar nuevo
                        logger.info(f"Giveaway board: mensaje incompatible en {guild.name} (400), enviando nuevo.")
                        cfg["giveaway_message_id"] = None
                        await guardar_config_async()
                        if msg:
                            try:
                                await msg.delete()
                            except Exception:
                                pass
                    else:
                        logger.warning(f"Giveaway board: error HTTP {e.status} en {guild.name} — {e}")
                        continue
                except Exception as e:
                    logger.warning(f"Giveaway board: error editando en {guild.name} — {e}")
                    continue

            # Enviar mensaje nuevo (primera vez o tras borrado)
            try:
                nuevo_msg = await canal.send(embed=embed)
                cfg["giveaway_message_id"] = str(nuevo_msg.id)
                await guardar_config_async()
                logger.info(f"Giveaway board: nuevo mensaje enviado en {guild.name} (ID {nuevo_msg.id})")
            except discord.Forbidden:
                logger.warning(f"Giveaway board: sin permisos para enviar en {guild.name}")
            except Exception as e:
                logger.warning(f"Giveaway board: error enviando en {guild.name} — {e}")

        except Exception as e:
            logger.error(f"Giveaway board: error inesperado en guild {gid_str} — {e}")


@actualizar_giveaway_board.before_loop
async def before_giveaway_board():
    await bot.wait_until_ready()


# ==================================================================================================
# --- SISTEMA DE TICKETS ---
# TicketButtonView y TicketCloseView tienen timeout=None + custom_id fijo → sobreviven reinicios.
# TicketSetupView es efímero (solo el admin que abre /tickets lo ve).
# ==================================================================================================

def build_ticket_setup_embed(guild: discord.Guild) -> discord.Embed:
    cfg = get_guild_config(guild.id)
    gid = guild.id
    ninguno = t(gid, "ticket_cfg_ninguno")

    canal_id = cfg.get("ticket_canal_soporte")
    canal_txt = f"<#{canal_id}>" if canal_id else ninguno

    cat_id = cfg.get("ticket_categoria")
    cat_txt = f"<#{cat_id}>" if cat_id else ninguno

    logs_id = cfg.get("ticket_logs")
    logs_txt = f"<#{logs_id}>" if logs_id else ninguno

    rol_id = cfg.get("ticket_rol_soporte")
    rol_txt = f"<@&{rol_id}>" if rol_id else ninguno

    contador = cfg.get("ticket_contador", 0)

    embed = discord.Embed(
        title=t(gid, "ticket_cfg_titulo"),
        description=t(gid, "ticket_cfg_desc"),
        color=COLORS["ticket"]
    )
    embed.add_field(name=f"📢 {t(gid, 'ticket_cfg_canal')}",    value=canal_txt,  inline=True)
    embed.add_field(name=f"📁 {t(gid, 'ticket_cfg_categoria')}", value=cat_txt,   inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)
    embed.add_field(name=f"📋 {t(gid, 'ticket_cfg_logs')}",      value=logs_txt,  inline=True)
    embed.add_field(name=f"🛡️ {t(gid, 'ticket_cfg_rol')}",      value=rol_txt,   inline=True)
    embed.add_field(name=f"🎫 {t(gid, 'ticket_cfg_contador')}",  value=f"`{contador}`", inline=True)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=f"{guild.name} • AegisBot Tickets", icon_url=guild.icon.url if guild.icon else None)
    embed.timestamp = discord.utils.utcnow()
    return embed


# --- Selects del panel de configuración de tickets ---

class TicketCanalSelect(ui.Select):
    def __init__(self, guild: discord.Guild, panel_msg, authorized_user_id: int):
        self.guild_id = guild.id
        self.panel_msg = panel_msg
        self.authorized_user_id = authorized_user_id
        opciones = [
            discord.SelectOption(label=f"# {c.name}"[:100], value=str(c.id))
            for c in guild.text_channels
        ][:25] or [discord.SelectOption(label="Sin canales", value="none")]
        super().__init__(placeholder=t(guild.id, "selecciona_canal_ticket"), options=opciones)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("Sin canales disponibles.", ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        cfg["ticket_canal_soporte"] = self.values[0]
        await guardar_config_async()
        canal = interaction.guild.get_channel(int(self.values[0]))
        await interaction.response.send_message(
            t(self.guild_id, "ticket_cfg_canal_set", canal=canal.mention if canal else self.values[0]),
            ephemeral=True
        )
        if self.panel_msg:
            try:
                await self.panel_msg.edit(
                    embed=build_ticket_setup_embed(interaction.guild),
                    view=TicketSetupView(interaction.guild, self.panel_msg, self.authorized_user_id)
                )
            except Exception as e:
                logger.warning(f"Ticket setup panel update error: {e}")


class TicketCategoriaSelect(ui.Select):
    def __init__(self, guild: discord.Guild, panel_msg, authorized_user_id: int):
        self.guild_id = guild.id
        self.panel_msg = panel_msg
        self.authorized_user_id = authorized_user_id
        opciones = [
            discord.SelectOption(label=c.name[:100], value=str(c.id))
            for c in guild.categories
        ][:25] or [discord.SelectOption(label="Sin categorías", value="none")]
        super().__init__(placeholder=t(guild.id, "selecciona_categoria_ticket"), options=opciones)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("Sin categorías disponibles.", ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        cfg["ticket_categoria"] = self.values[0]
        await guardar_config_async()
        cat = interaction.guild.get_channel(int(self.values[0]))
        await interaction.response.send_message(
            t(self.guild_id, "ticket_cfg_categoria_set", categoria=cat.name if cat else self.values[0]),
            ephemeral=True
        )
        if self.panel_msg:
            try:
                await self.panel_msg.edit(
                    embed=build_ticket_setup_embed(interaction.guild),
                    view=TicketSetupView(interaction.guild, self.panel_msg, self.authorized_user_id)
                )
            except Exception as e:
                logger.warning(f"Ticket setup panel update error: {e}")


class TicketLogsSelect(ui.Select):
    def __init__(self, guild: discord.Guild, panel_msg, authorized_user_id: int):
        self.guild_id = guild.id
        self.panel_msg = panel_msg
        self.authorized_user_id = authorized_user_id
        opciones = [
            discord.SelectOption(label=f"# {c.name}"[:100], value=str(c.id))
            for c in guild.text_channels
        ][:25] or [discord.SelectOption(label="Sin canales", value="none")]
        super().__init__(placeholder=t(guild.id, "selecciona_logs_ticket"), options=opciones)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("Sin canales disponibles.", ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        cfg["ticket_logs"] = self.values[0]
        await guardar_config_async()
        canal = interaction.guild.get_channel(int(self.values[0]))
        await interaction.response.send_message(
            t(self.guild_id, "ticket_cfg_logs_set", canal=canal.mention if canal else self.values[0]),
            ephemeral=True
        )
        if self.panel_msg:
            try:
                await self.panel_msg.edit(
                    embed=build_ticket_setup_embed(interaction.guild),
                    view=TicketSetupView(interaction.guild, self.panel_msg, self.authorized_user_id)
                )
            except Exception as e:
                logger.warning(f"Ticket setup panel update error: {e}")


class TicketRolSelect(ui.Select):
    def __init__(self, guild: discord.Guild, panel_msg, authorized_user_id: int):
        self.guild_id = guild.id
        self.panel_msg = panel_msg
        self.authorized_user_id = authorized_user_id
        opciones = [
            discord.SelectOption(label=r.name[:100], value=str(r.id))
            for r in guild.roles
            if not r.is_bot_managed() and r.name != "@everyone"
        ][:25] or [discord.SelectOption(label="Sin roles", value="none")]
        super().__init__(placeholder=t(guild.id, "selecciona_rol_ticket"), options=opciones)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("Sin roles disponibles.", ephemeral=True)
            return
        cfg = get_guild_config(self.guild_id)
        cfg["ticket_rol_soporte"] = self.values[0]
        await guardar_config_async()
        rol = interaction.guild.get_role(int(self.values[0]))
        await interaction.response.send_message(
            t(self.guild_id, "ticket_cfg_rol_set", rol=rol.mention if rol else self.values[0]),
            ephemeral=True
        )
        if self.panel_msg:
            try:
                await self.panel_msg.edit(
                    embed=build_ticket_setup_embed(interaction.guild),
                    view=TicketSetupView(interaction.guild, self.panel_msg, self.authorized_user_id)
                )
            except Exception as e:
                logger.warning(f"Ticket setup panel update error: {e}")


# --- Panel de configuración principal ---

class TicketSetupView(ui.View):
    def __init__(self, guild: discord.Guild, panel_msg=None, authorized_user_id: int = None):
        super().__init__(timeout=300)
        self.guild = guild
        self.panel_msg = panel_msg
        self.authorized_user_id = authorized_user_id

    def _check(self, interaction: discord.Interaction) -> bool:
        return self.authorized_user_id is None or interaction.user.id == self.authorized_user_id

    @ui.button(label="📢 Canal del Panel", style=discord.ButtonStyle.primary, row=0)
    async def btn_canal(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        view = ui.View(timeout=60)
        view.add_item(TicketCanalSelect(self.guild, self.panel_msg, self.authorized_user_id))
        await interaction.response.send_message(
            t(self.guild.id, "selecciona_canal_ticket"), view=view, ephemeral=True
        )

    @ui.button(label="📁 Categoría", style=discord.ButtonStyle.primary, row=0)
    async def btn_categoria(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        view = ui.View(timeout=60)
        view.add_item(TicketCategoriaSelect(self.guild, self.panel_msg, self.authorized_user_id))
        await interaction.response.send_message(
            t(self.guild.id, "selecciona_categoria_ticket"), view=view, ephemeral=True
        )

    @ui.button(label="📋 Canal de Logs", style=discord.ButtonStyle.primary, row=0)
    async def btn_logs(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        view = ui.View(timeout=60)
        view.add_item(TicketLogsSelect(self.guild, self.panel_msg, self.authorized_user_id))
        await interaction.response.send_message(
            t(self.guild.id, "selecciona_logs_ticket"), view=view, ephemeral=True
        )

    @ui.button(label="🛡️ Rol de Soporte", style=discord.ButtonStyle.primary, row=0)
    async def btn_rol(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        view = ui.View(timeout=60)
        view.add_item(TicketRolSelect(self.guild, self.panel_msg, self.authorized_user_id))
        await interaction.response.send_message(
            t(self.guild.id, "selecciona_rol_ticket"), view=view, ephemeral=True
        )

    @ui.button(label="✅ Finalizar Configuración", style=discord.ButtonStyle.success, row=1)
    async def btn_publicar(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild.id)
        canal_id = cfg.get("ticket_canal_soporte")
        if not canal_id:
            await interaction.response.send_message(
                t(self.guild.id, "ticket_cfg_sin_canal"), ephemeral=True
            )
            return

        canal = self.guild.get_channel(int(canal_id))
        if not canal:
            await interaction.response.send_message("❌ Canal no encontrado. Selecciónalo de nuevo.", ephemeral=True)
            return

        gid = self.guild.id
        embed_panel = discord.Embed(
            title=t(gid, "ticket_panel_titulo"),
            description=t(gid, "ticket_panel_desc"),
            color=COLORS["ticket"]
        )
        embed_panel.set_thumbnail(url=bot.user.display_avatar.url)
        if self.guild.icon:
            embed_panel.set_image(url=self.guild.icon.url)
        embed_panel.set_footer(
            text=f"{self.guild.name} • AegisBot",
            icon_url=self.guild.icon.url if self.guild.icon else None
        )
        embed_panel.timestamp = discord.utils.utcnow()

        try:
            await canal.send(embed=embed_panel, view=TicketButtonView())
        except discord.Forbidden:
            await interaction.response.send_message(t(gid, "sin_permisos_bot"), ephemeral=True)
            return
        except Exception as e:
            logger.error(f"Error publicando panel de tickets: {e}")
            await interaction.response.send_message("❌ Error al publicar el panel.", ephemeral=True)
            return

        # Cierra el panel de setup y confirma
        done_embed = discord.Embed(
            title="✅ Configuración completada",
            description=f"El panel de tickets fue publicado en {canal.mention}.\nLos usuarios ya pueden abrir tickets desde allí.",
            color=COLORS["ok"]
        )
        done_embed.set_footer(text=f"{self.guild.name} • AegisBot Tickets")
        done_embed.timestamp = discord.utils.utcnow()
        await interaction.response.edit_message(embed=done_embed, view=None)

    @ui.button(label="♻️ Resetear Config", style=discord.ButtonStyle.secondary, row=1)
    async def btn_reset(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        cfg = get_guild_config(self.guild.id)
        cfg["ticket_canal_soporte"] = None
        cfg["ticket_categoria"] = None
        cfg["ticket_logs"] = None
        cfg["ticket_rol_soporte"] = None
        await guardar_config_async()
        await interaction.response.edit_message(
            embed=build_ticket_setup_embed(self.guild),
            view=TicketSetupView(self.guild, self.panel_msg, self.authorized_user_id)
        )
        await interaction.followup.send("♻️ Configuración de tickets reseteada.", ephemeral=True)

    @ui.button(label="❌ Cerrar", style=discord.ButtonStyle.danger, row=1)
    async def btn_cerrar(self, interaction: discord.Interaction, button: ui.Button):
        if not self._check(interaction):
            await interaction.response.send_message(t(self.guild.id, "solo_admin_boton"), ephemeral=True)
            return
        await interaction.response.edit_message(content="✅ Panel cerrado.", embed=None, view=None)


# --- Views persistentes (sobreviven reinicios) ---

# Colores por tipo de ticket
TICKET_TIPO_COLORS = {
    "soporte":   0x5865F2,
    "reporte":   0xEF4444,
    "apelacion": 0xF59E0B,
}
TICKET_TIPO_EMOJIS = {
    "soporte":   "🛠️",
    "reporte":   "🚨",
    "apelacion": "⚖️",
}


async def _crear_canal_ticket(interaction: discord.Interaction, tipo: str):
    """Lógica común para crear un canal de ticket de cualquier tipo."""
    gid = interaction.guild.id
    cfg = get_guild_config(gid)

    nombre_canal = f"ticket-{tipo}-{interaction.user.name.lower().replace(' ', '-')}"
    # Buscar si ya tiene un ticket abierto de ese tipo
    canal_existente = discord.utils.get(interaction.guild.text_channels, name=nombre_canal)
    if canal_existente:
        await interaction.response.send_message(
            t(gid, "ticket_ya_abierto", canal=canal_existente.mention), ephemeral=True
        )
        return

    categoria = None
    cat_id = cfg.get("ticket_categoria")
    if cat_id:
        categoria = interaction.guild.get_channel(int(cat_id))

    cfg["ticket_contador"] = cfg.get("ticket_contador", 0) + 1
    numero = cfg["ticket_contador"]
    await guardar_config_async()

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
    }
    rol_id = cfg.get("ticket_rol_soporte")
    if rol_id:
        rol = interaction.guild.get_role(int(rol_id))
        if rol:
            overwrites[rol] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    try:
        canal = await interaction.guild.create_text_channel(
            name=nombre_canal,
            overwrites=overwrites,
            category=categoria,
            topic=f"Ticket #{numero} [{tipo.upper()}] — {interaction.user} ({interaction.user.id})"
        )
    except discord.Forbidden:
        await interaction.response.send_message(t(gid, "sin_permisos_bot"), ephemeral=True)
        return
    except Exception as e:
        logger.error(f"Error creando canal de ticket: {e}")
        await interaction.response.send_message("❌ Error al crear el ticket.", ephemeral=True)
        return

    emoji = TICKET_TIPO_EMOJIS.get(tipo, "🎫")
    color = TICKET_TIPO_COLORS.get(tipo, COLORS["ticket"])

    embed = discord.Embed(
        title=f"{emoji} Ticket #{numero} — {tipo.capitalize()}",
        description=t(gid, "ticket_embed_desc", mencion=interaction.user.mention),
        color=color
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.add_field(name="👤 Usuario", value=f"{interaction.user.mention} • ID: `{interaction.user.id}`", inline=False)
    embed.add_field(name="🔢 Ticket", value=f"`#{numero}`", inline=True)
    embed.add_field(name="📋 Tipo", value=f"{emoji} {tipo.capitalize()}", inline=True)
    embed.add_field(name="📅 Abierto", value=f"<t:{int(discord.utils.utcnow().timestamp())}:R>", inline=True)
    embed.set_footer(text="AegisBot • Soporte", icon_url=bot.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()

    await canal.send(content=interaction.user.mention, embed=embed, view=TicketCloseView())
    await interaction.response.send_message(t(gid, "ticket_abierto", canal=canal.mention), ephemeral=True)

    logs_id = cfg.get("ticket_logs")
    if logs_id:
        log_canal = interaction.guild.get_channel(int(logs_id))
        if log_canal:
            log_embed = discord.Embed(
                title=f"{emoji} Ticket abierto — {tipo.capitalize()}",
                description=f"**{interaction.user.mention}** abrió el ticket `#{numero}`.",
                color=color
            )
            log_embed.add_field(name="📋 Canal", value=canal.mention, inline=True)
            log_embed.add_field(name="👤 Usuario", value=f"`{interaction.user}` • ID: `{interaction.user.id}`", inline=True)
            log_embed.set_footer(text="AegisBot • Tickets", icon_url=bot.user.display_avatar.url)
            log_embed.timestamp = discord.utils.utcnow()
            try:
                await log_canal.send(embed=log_embed)
            except Exception as e:
                logger.warning(f"Error enviando log de ticket abierto: {e}")


class TicketTipoSelect(ui.Select):
    """Select de tipo de ticket. Se crea por interacción, no persiste."""
    def __init__(self, gid: int):
        opciones = [
            discord.SelectOption(
                label="Soporte",
                description="Ayuda general con el servidor",
                value="soporte",
                emoji="🛠️"
            ),
            discord.SelectOption(
                label="Reporte",
                description="Reportar a un usuario",
                value="reporte",
                emoji="🚨"
            ),
            discord.SelectOption(
                label="Apelación",
                description="Apelar una sanción recibida",
                value="apelacion",
                emoji="⚖️"
            ),
        ]
        super().__init__(
            placeholder=t(gid, "ticket_selecciona_tipo"),
            options=opciones,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        tipo = self.values[0]
        await _crear_canal_ticket(interaction, tipo)


class TicketButtonView(ui.View):
    """Panel público de soporte. Persiste entre reinicios."""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="🎫 Abrir Ticket", style=discord.ButtonStyle.primary, custom_id="aegis_open_ticket")
    async def abrir_ticket(self, interaction: discord.Interaction, button: ui.Button):
        gid = interaction.guild.id
        cfg = get_guild_config(gid)

        # Verificar que el sistema esté configurado
        if not cfg.get("ticket_canal_soporte"):
            await interaction.response.send_message(t(gid, "ticket_sin_config"), ephemeral=True)
            return

        # Mostrar select de tipo de ticket
        view = ui.View(timeout=60)
        view.add_item(TicketTipoSelect(gid))
        await interaction.response.send_message(
            t(gid, "ticket_selecciona_tipo"), view=view, ephemeral=True
        )




class TicketCloseView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="🗑️ Cerrar y Borrar Ticket", style=discord.ButtonStyle.danger, custom_id="aegis_close_ticket")
    async def cerrar_ticket(self, interaction: discord.Interaction, button: ui.Button):
        gid = interaction.guild.id
        cfg = get_guild_config(gid)
        canal = interaction.channel

        # Solo mods/admins pueden cerrar — el usuario que abrió el ticket no puede borrarlo
        if not tiene_permiso_mod(interaction.user, cfg):
            await interaction.response.send_message(t(gid, "sin_permisos"), ephemeral=True)
            return

        await interaction.response.defer()

        # Recopilar mensajes para el transcript
        msgs_transcript = []
        try:
            async for msg in canal.history(limit=200, oldest_first=True):
                if msg.author.bot and not msg.content and not msg.embeds:
                    continue
                msgs_transcript.append(msg)
        except Exception as e:
            logger.warning(f"Error recopilando transcript: {e}")

        logs_id = cfg.get("ticket_logs")
        if logs_id:
            log_canal = interaction.guild.get_channel(int(logs_id))
            if log_canal:
                # Generar HTML del transcript
                nombre_ticket = canal.name
                cerrado_por = str(interaction.user)
                fecha_cierre = discord.utils.utcnow().strftime("%d/%m/%Y %H:%M UTC")

                filas_html = ""
                for msg in msgs_transcript:
                    ts = msg.created_at.strftime("%H:%M")
                    autor = msg.author.display_name
                    contenido = msg.content or ""
                    # Adjuntos
                    for att in msg.attachments:
                        contenido += f" [adjunto: {att.filename}]"
                    # Embeds
                    for emb in msg.embeds:
                        titulo_emb = emb.title or ""
                        contenido += f" [embed: {titulo_emb}]"
                    contenido = contenido.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                    es_bot = "bot" if msg.author.bot else ""
                    filas_html += f'<tr class="{es_bot}"><td class="ts">{ts}</td><td class="autor">{autor}</td><td class="msg">{contenido}</td></tr>\n'

                html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Transcript — {nombre_ticket}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #1e1f2e; color: #c9cdd4; margin: 0; padding: 20px; }}
  h1 {{ color: #7289da; border-bottom: 2px solid #7289da; padding-bottom: 8px; }}
  .meta {{ color: #72767d; font-size: 0.85em; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  tr:nth-child(even) {{ background: #2a2d3e; }}
  td {{ padding: 6px 10px; vertical-align: top; }}
  .ts {{ color: #72767d; white-space: nowrap; width: 50px; font-size: 0.85em; }}
  .autor {{ color: #7289da; white-space: nowrap; width: 160px; font-weight: bold; }}
  .msg {{ word-break: break-word; }}
  tr.bot .autor {{ color: #43b581; }}
</style>
</head>
<body>
<h1>📋 Transcript — {nombre_ticket}</h1>
<div class="meta">
  Cerrado por: <strong>{cerrado_por}</strong> &nbsp;|&nbsp;
  Fecha: <strong>{fecha_cierre}</strong> &nbsp;|&nbsp;
  Mensajes: <strong>{len(msgs_transcript)}</strong>
</div>
<table>
  <thead><tr><th>Hora</th><th>Usuario</th><th>Mensaje</th></tr></thead>
  <tbody>
{filas_html}  </tbody>
</table>
</body>
</html>"""

                html_bytes = html.encode("utf-8")
                archivo = discord.File(
                    fp=io.BytesIO(html_bytes),
                    filename=f"transcript-{nombre_ticket}.html"
                )
                log_embed = discord.Embed(
                    title=t(gid, "ticket_transcript_titulo"),
                    description=f"Canal: **{nombre_ticket}** · Cerrado por: **{cerrado_por}**",
                    color=COLORS["ticket_cerrado"]
                )
                log_embed.set_footer(text="AegisBot • Tickets", icon_url=bot.user.display_avatar.url)
                log_embed.timestamp = discord.utils.utcnow()
                try:
                    await log_canal.send(embed=log_embed, file=archivo)
                except Exception as e:
                    logger.warning(f"Error enviando transcript HTML: {e}")

        try:
            await canal.send(t(gid, "ticket_cerrado_msg", usuario=str(interaction.user)))
            await asyncio.sleep(3)
        except Exception:
            pass

        try:
            await canal.delete(reason=f"Ticket cerrado por {interaction.user}")
        except discord.Forbidden:
            await interaction.followup.send(t(gid, "sin_permisos_bot"), ephemeral=True)
        except Exception as e:
            logger.error(f"Error eliminando canal de ticket: {e}")


@bot.tree.command(name="tickets", description="Configura el sistema de tickets / Configure the ticket system.")
async def tickets_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t(interaction.guild.id, "solo_admin"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    view = TicketSetupView(interaction.guild, authorized_user_id=interaction.user.id)
    panel = await interaction.followup.send(
        embed=build_ticket_setup_embed(interaction.guild),
        view=view,
        ephemeral=True,
        wait=True
    )
    view.panel_msg = panel

# --- comandos de APIs (sin API keys, vía aiohttp) ---

@bot.tree.command(name='clima', description='Muestra el clima actual de una ciudad.')
@app_commands.describe(ciudad='Ciudad a consultar (ej: Madrid, Buenos Aires)')
async def clima(interaction: discord.Interaction, ciudad: str):
    await interaction.response.defer()
    gid = interaction.guild.id if interaction.guild else 0

    url = f"https://wttr.in/{ciudad.replace(' ', '+')}?format=j1&lang=es"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    await interaction.followup.send(t(gid, "clima_error", ciudad=ciudad))
                    return
                data = await resp.json(content_type=None)
    except asyncio.TimeoutError:
        await interaction.followup.send(t(gid, "clima_error", ciudad=ciudad))
        return
    except Exception as e:
        logger.warning(f"Error API clima: {e}")
        await interaction.followup.send(t(gid, "clima_error", ciudad=ciudad))
        return

    try:
        actual = data["current_condition"][0]
        nombre_lugar = data["nearest_area"][0]["areaName"][0]["value"]
        pais = data["nearest_area"][0]["country"][0]["value"]
        temp_c = actual["temp_C"]
        temp_f = actual["temp_F"]
        humedad = actual["humidity"]
        viento_kmh = actual["windspeedKmph"]
        sensacion = actual["FeelsLikeC"]
        descripcion = actual["weatherDesc"][0]["value"]
        visibilidad = actual["visibility"]

        # Emoji según temperatura
        temp_int = int(temp_c)
        if temp_int >= 30:
            emoji_temp = "🔥"
        elif temp_int >= 20:
            emoji_temp = "☀️"
        elif temp_int >= 10:
            emoji_temp = "🌤️"
        elif temp_int >= 0:
            emoji_temp = "🌨️"
        else:
            emoji_temp = "🥶"

        embed = discord.Embed(
            title=t(gid, "clima_titulo", ciudad=f"{nombre_lugar}, {pais}"),
            description=f"**{descripcion}** {emoji_temp}",
            color=COLORS["clima"]
        )
        embed.add_field(name="🌡️ Temperatura", value=f"`{temp_c}°C` / `{temp_f}°F`", inline=True)
        embed.add_field(name="🤔 Sensación", value=f"`{sensacion}°C`", inline=True)
        embed.add_field(name="💧 Humedad", value=f"`{humedad}%`", inline=True)
        embed.add_field(name="💨 Viento", value=f"`{viento_kmh} km/h`", inline=True)
        embed.add_field(name="👁️ Visibilidad", value=f"`{visibilidad} km`", inline=True)
        embed.set_footer(text="AegisBot • Clima · wttr.in", icon_url=bot.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)
    except (KeyError, IndexError) as e:
        logger.warning(f"Error parseando respuesta de clima: {e}")
        await interaction.followup.send(t(gid, "clima_error", ciudad=ciudad))


@bot.tree.command(name='giveaway', description='Muestra juegos y loot gratis activos ahora mismo.')
@app_commands.describe(plataforma='Filtrar por plataforma (opcional)')
@app_commands.choices(plataforma=[
    app_commands.Choice(name='🖥️ PC',             value='pc'),
    app_commands.Choice(name='🟦 Steam',           value='steam'),
    app_commands.Choice(name='🎮 Epic Games Store',value='epic-games-store'),
    app_commands.Choice(name='🎮 PlayStation',     value='ps4'),
    app_commands.Choice(name='🟩 Xbox',            value='xbox-one'),
    app_commands.Choice(name='🔴 Nintendo Switch', value='switch'),
    app_commands.Choice(name='📱 Android',         value='android'),
    app_commands.Choice(name='🍎 iOS',             value='ios'),
])
async def giveaway(interaction: discord.Interaction, plataforma: app_commands.Choice[str] = None):
    await interaction.response.defer()
    gid = interaction.guild.id if interaction.guild else 0

    # Construir URL con o sin filtro de plataforma
    if plataforma:
        url = f"https://www.gamerpower.com/api/giveaways?platform={plataforma.value}&sort-by=popularity"
    else:
        url = "https://www.gamerpower.com/api/giveaways?sort-by=popularity"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 201:
                    # 201 = no hay giveaways activos
                    await interaction.followup.send(t(gid, "giveaway_error"))
                    return
                if resp.status != 200:
                    await interaction.followup.send(t(gid, "giveaway_error"))
                    return
                data = await resp.json(content_type=None)
    except asyncio.TimeoutError:
        await interaction.followup.send(t(gid, "giveaway_error"))
        return
    except Exception as e:
        logger.warning(f"Error API giveaway: {e}")
        await interaction.followup.send(t(gid, "giveaway_error"))
        return

    if not data or not isinstance(data, list):
        await interaction.followup.send(t(gid, "giveaway_error"))
        return

    # Filtrar por plataforma si se especificó
    if plataforma:
        data_filtrada = [g for g in data if plataforma.value.lower() in g.get("platforms", "").lower()]
        if not data_filtrada:
            await interaction.followup.send(t(gid, "giveaway_error"))
            return
        embed = build_giveaway_board_embed(gid, data_filtrada)
        embed.title = f"🎮 Giveaways — {plataforma.name}"
    else:
        embed = build_giveaway_board_embed(gid, data)

    await interaction.followup.send(embed=embed)


# ==================================================================================================
# --- SISTEMA DE REPORTES GLOBAL ---
# reportes_globales: {str(user_id): {"motivo": str, "reportado_por": str, "servidor": str}}
# Se guarda en server_config bajo la clave especial "__reportes__"
# ==================================================================================================

def get_reportes() -> dict:
    return reportes_globales

def guardar_reportes():
    _guardar_reportes_file(reportes_globales)

@bot.tree.command(name="reportar", description="Reporta a un usuario globalmente.")
@app_commands.describe(
    miembro="Selecciona al usuario del servidor",
    usuario_id="ID numérico si el usuario ya no está en el servidor",
    motivo="Motivo del reporte"
)
async def reportar(interaction: discord.Interaction, motivo: str, miembro: discord.Member = None, usuario_id: str = None):
    gid = interaction.guild.id
    cfg = get_guild_config(gid)
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "solo_mod"), ephemeral=True)
        return

    if not miembro and not usuario_id:
        await interaction.response.send_message("❌ Debes seleccionar un miembro o proporcionar un ID.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    # Resolver usuario: miembro del servidor tiene prioridad sobre ID manual
    if miembro:
        user_obj = miembro
    else:
        uid_str = usuario_id.strip().strip("<@!>")
        try:
            uid_int = int(uid_str)
        except ValueError:
            await interaction.followup.send("❌ ID inválido. Debe ser un número.", ephemeral=True)
            return
        user_obj = bot.get_user(uid_int)
        if user_obj is None:
            try:
                user_obj = await bot.fetch_user(uid_int)
            except discord.NotFound:
                await interaction.followup.send("❌ No encontré ese usuario. Verifica el ID.", ephemeral=True)
                return
            except Exception as e:
                logger.warning(f"reportar: error fetch_user {uid_int} — {e}")
                await interaction.followup.send(f"❌ Error al buscar el usuario: {e}", ephemeral=True)
                return

    uid_int = user_obj.id

    reportes = get_reportes()
    uid = str(uid_int)
    if uid in reportes:
        await interaction.followup.send(t(gid, "reporte_ya_existe"), ephemeral=True)
        return

    reportes[uid] = {
        "motivo": motivo,
        "servidor": interaction.guild.name,
        "servidor_id": str(gid),
    }
    await guardar_reportes_async()

    embed = discord.Embed(
        title="🚨 Nuevo reporte global",
        description=f"**{user_obj}** (`{user_obj.id}`) fue reportado.",
        color=COLORS["spam"]
    )
    embed.set_thumbnail(url=user_obj.display_avatar.url)
    embed.add_field(name=f"📝 {t(gid, 'reporte_motivo_label')}", value=motivo, inline=False)
    embed.add_field(name=f"🏠 {t(gid, 'reporte_en_servidor')}", value=interaction.guild.name, inline=True)
    embed.set_footer(text="AegisBot • Reportes Globales", icon_url=bot.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()

    await interaction.followup.send(t(gid, "reporte_agregado", usuario=str(user_obj), motivo=motivo), ephemeral=True)


@bot.tree.command(name="quitar_reporte", description="Elimina el reporte global de un usuario (@mención o ID).")
@app_commands.describe(usuario="@mención o ID del usuario")
async def quitar_reporte(interaction: discord.Interaction, usuario: str):
    gid = interaction.guild.id
    cfg = get_guild_config(gid)
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "solo_mod"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    uid_str = usuario.strip().strip("<@!>")
    try:
        uid_int = int(uid_str)
    except ValueError:
        await interaction.followup.send("❌ Formato inválido. Usa @mención o el ID numérico.", ephemeral=True)
        return

    reportes = get_reportes()
    uid = str(uid_int)
    if uid not in reportes:
        await interaction.followup.send(t(gid, "reporte_no_existe"), ephemeral=True)
        return

    del reportes[uid]
    await guardar_reportes_async()
    await interaction.followup.send(t(gid, "reporte_quitado", usuario=uid), ephemeral=True)


@bot.tree.command(name="reportes", description="Muestra la lista de usuarios reportados globalmente.")
async def lista_reportes(interaction: discord.Interaction):
    gid = interaction.guild.id
    cfg = get_guild_config(gid)
    if not tiene_permiso_mod(interaction.user, cfg):
        await interaction.response.send_message(t(gid, "solo_mod"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    reportes = get_reportes()
    if not reportes:
        await interaction.followup.send(t(gid, "reporte_lista_vacia"), ephemeral=True)
        return

    embed = discord.Embed(
        title=t(gid, "reporte_lista_titulo"),
        color=COLORS["spam"]
    )
    for uid, info in list(reportes.items())[:15]:
        user = bot.get_user(int(uid))
        nombre = str(user) if user else f"ID: {uid}"
        embed.add_field(
            name=f"🔴 {nombre}",
            value=(
                f"📝 {info.get('motivo', '?')}\n"
                f"🏠 {info.get('servidor', '?')}"
            ),
            inline=False
        )
    embed.set_footer(text=f"AegisBot • Reportes Globales · {len(reportes)} total", icon_url=bot.user.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed, ephemeral=True)



if __name__ == "__main__":
    import time as _time
    while True:
        try:
            bot.run(CONFIG["TOKEN"])
        except discord.errors.LoginFailure:
            logger.error("Token inválido.")
            break
        except discord.errors.PrivilegedIntentsRequired:
            logger.error("Intents privilegiados no habilitados en el portal de desarrolladores.")
            break
        except KeyboardInterrupt:
            logger.info("Bot apagado manualmente.")
            break
        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"Bot crasheó: {e} — reiniciando en 10s")
            _time.sleep(10)
