# 🛡️ AegisBot / Orion

AegisBot es una solución integral de moderación y seguridad para servidores de Discord, diseñada para ofrecer protección avanzada contra raids, spam y contenido malicioso, manteniendo una interfaz limpia y profesional.

---

## ✨ Características Principales

- 🛡️ **Sistema Antiraid** — Detección inteligente de ingresos masivos y bloqueos automáticos para proteger la integridad del servidor.
- 🚫 **Automod Avanzado** — Filtros personalizables para enlaces, invitaciones no autorizadas, palabras prohibidas y detección de spam por repetición.
- 🎫 **Sistema de Tickets** — Gestión de soporte mediante canales privados con transcripciones automáticas.
- 📊 **Registro de Auditoría** — Logs detallados sobre ediciones de mensajes, eliminaciones y cambios en los miembros del equipo.
- 🖼️ **Bienvenidas Personalizadas** — Generación dinámica de imágenes de bienvenida utilizando procesamiento nativo.
- ⚙️ **Configuración Dinámica** — Panel de configuración por servidor guardado en JSON para una persistencia de datos ligera y rápida.

---

## 🚀 Instalación y Despliegue

### Requisitos Previos

- Python 3.10 o superior
- Librerías necesarias:

```bash
pip install discord.py Pillow requests aiohttp
```

### Configuración

1. Clona el repositorio:

```bash
git clone https://github.com/TuUsuario/AegisBot.git
```

2. Crea un archivo `.env` o coloca tu token en el script principal (no recomendado para repositorios públicos).

3. Activa los **Privileged Gateway Intents** (Members, Presences y Message Content) en el [Discord Developer Portal](https://discord.com/developers/applications).

---

## 🛠️ Tecnologías Utilizadas

| Componente | Tecnología |
|---|---|
| Lenguaje | Python |
| Librería principal | discord.py |
| Procesamiento de imágenes | Pillow (PIL) |
| Persistencia | JSON dinámico |

---

## 🔐 Seguridad

El bot incluye un sistema de recuperación ante errores que mantiene el servicio activo ante fallos inesperados de conexión, además de un manejo optimizado de hilos para no comprometer el rendimiento del servidor donde se aloje.
