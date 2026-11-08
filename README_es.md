![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/36fb04e4-cc75-4454-bd8b-049d11aa86f9)

<div align="center">

<a href="./README.md">English</a> ｜ <a href="./README_zh.md">简体中文</a> ｜ <a href="./README_zh-TW.md">繁體中文</a> ｜ <a href="./README_ja.md">日本語</a> ｜ <a href="./README_fr.md">Français</a> ｜ Español ｜ <a href="./README_ru.md">Русский</a>

<br>
<br>

[![version](https://img.shields.io/badge/version-4.29.4%2Bmtn1-blue)](https://github.com/Chenamel/astrbot-maintained/releases)
[![license](https://img.shields.io/badge/license-AGPL--3.0-green)](./LICENSE)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](./pyproject.toml)

</div>

Esta es una rama mantenida de AstrBot, con su línea base fijada en la versión `v4.29.4` upstream. El repositorio se mantiene de forma independiente y no forma parte de la red de forks de GitHub. Los paquetes de distribución contienen únicamente el core en sí, sin plugins. La licencia es AGPL-3.0-or-later, sin afiliación alguna con los autores upstream.

## Diferencias principales y nuevas API

La versión oficial upstream no hace públicos ciertos estados subyacentes. Este fork añade interfaces bajo `astrbot/api/**` para exponer dichos estados.

Hay un total de 10 archivos nuevos o modificados bajo `astrbot/api/`, de los cuales 8 son módulos funcionales y 2 son archivos auxiliares. Cada módulo funcional proporciona una función `available()`. En el entorno original upstream, `available()` devuelve `False`.

| Módulo | Descripción de funciones | Interfaces principales |
|---|---|---|
| `api.turns` | Evaluación del estado del turno, obtención de texto sin procesar e imágenes combinadas | `is_current` / `merged_text` / `merged_image_urls` / `mark_sent` |
| `api.proactive` | Generación de respuestas proactivas conectada a la personalidad y a la cadena de memoria | `generate_with_persona` / `persona_available` |
| `api.delivery` | Evaluación de la estrategia de entrega, diferenciando entre mensajes de texto y entrega de archivos | `resolve` / `has_code_delivery` / `code_task_spec` |
| `api.permissions` | Evaluación de la autorización de ejecución, diferenciando la identidad de administrador de la autorización por ejecución | `execution_denial` / `is_admin` |
| `api.media` | Evaluación de disponibilidad de entrada visual y detección de descripciones de imágenes | `has_visual_input` / `image_input_available` / `has_image_caption` |
| `api.content` | Evaluación del tipo de segmento de mensaje | `is_text_part` / `is_image_part` |
| `api.runtime` | Rutas de ejecución, formateo de hora, descarga de imágenes y modo de temporización | `get_astrbot_data_path` / `download_image_by_url` / `hook_timing_mode` |
| `api.embedding` | Evaluación del proveedor de vectorización | `is_embedding_provider` |
| `api.event.extras` | Contenedor de información adicional de eventos | Ver protocolo de información adicional de eventos |
| `api._bridge` | Capa de puente interno para la coordinación entre módulos; los plugins no deben llamarla directamente | — |

En la versión original upstream, `Context.llm_generate` llama directamente al proveedor del modelo subyacente, omitiendo el hook `on_llm_request`, lo que inhabilita los plugins de personalidad y memoria. `generate_with_persona` ejecuta primero el hook de solicitud, permitiendo que ambos plugins intervengan con normalidad.

## Opciones de configuración

Se han añadido 4 nuevas opciones de configuración, cuyos valores predeterminados coinciden con el comportamiento oficial upstream.

| Clave de configuración | Valor predeterminado | Descripción |
|---|---|---|
| `execution_gate_mode` | `legacy` | Modo de autorización de ejecución. Por defecto coincide con upstream; si se establece en `strict`, requiere que los mensajes soliciten explícitamente la ejecución |
| `hook_timing_mode` | `legacy` | Sincronización de activación del hook de finalización. Si se establece en `enhanced`, el hook se activa antes de enviar la respuesta |
| `direct_turn_quiet_sec` | `4` | Ventana de silencio de agregación de mensajes QQ en segundos. Si se establece en `0`, se desactiva la agregación y se procesa inmediatamente |
| `lightweight_proactive_tools` | Lista (29 elementos en total) | Lista blanca del conjunto de herramientas proactivas ligeras |

## Compatibilidad

El número de versión es `4.29.4+mtn1`. La parte `+mtn1` es el segmento local de PEP 440, que se ignora al comparar rangos de versiones.

| Método de declaración | Ejemplo | Criterio de compatibilidad |
|---|---|---|
| Declaración de rango | `>=4.16,<5` | Compatible |
| Coincidencia con línea base | `==4.29.4`, `~=4.28.0` | Compatible |
| Requisito de versión superior | `>=4.29` | Rechazado |
| Coincidencia estricta de igualdad | `===4.29.4` | Rechazado (las reglas de PEP 440 requieren igualdad total de cadenas) |

En las pruebas frente a la línea base, pasan tanto la suite de la versión mantenida como la de upstream; las pocas desviaciones conocidas se registran por separado.

## Instalación y ejecución

Requiere Python 3.12 o superior.

Aún no se ha publicado en PyPI; `pip install astrbot-maintained` no funcionará.

El paquete de distribución se llama `astrbot-maintained`, y el nombre de importación en Python es igualmente `astrbot`. Desinstale la versión oficial antes de instalar para evitar conflictos de nombres de importación.

### Instalación mediante wheel

Descargue el archivo `.whl` desde la página de Releases. El nombre del archivo contiene el carácter `+`, que en algunas consolas requiere comillas o secuencias de escape:

```bash
pip uninstall -y astrbot
pip install ./astrbot_maintained-4.29.4+mtn1-py3-none-any.whl
astrbot run
```

Inicie tras la instalación y acceda a `http://localhost:6185` en su navegador para entrar al panel de administración.

### Ejecución desde el código fuente

Clone este repositorio y ejecute con `uv`:

```bash
uv sync && uv run main.py
```

### Compilación propia de wheel

Al compilar manualmente un archivo wheel que incluya el panel WebUI, es necesario especificar la variable de entorno de compilación:

```bash
ASTRBOT_BUILD_DASHBOARD=1 uv build --wheel
```

Si no se establece esta variable de entorno, el resultado de la compilación no incluirá los archivos estáticos de WebUI.

## Comprobación de actualizaciones y sincronización con upstream

La comprobación de actualizaciones del panel apunta de forma predeterminada a las Releases de este repositorio:

- `update_source`: `https://api.github.com/repos/Chenamel/astrbot-maintained/releases`
- `update_repository`: `https://github.com/Chenamel/astrbot-maintained`

La arquitectura de `v4.29+` upstream ha cambiado y no contiene las API subyacentes añadidas aquí. Si se actualiza directamente a la versión oficial desde el panel, los archivos centrales modificados se sobrescribirán, provocando la pérdida de interfaces y errores de ejecución.

Si necesita volver a seguir las actualizaciones oficiales, cambie `update_source` a `https://api.soulter.top/releases` y `update_repository` a `https://github.com/AstrBotDevs/AstrBot` en el panel de administración.

## Documentación

- Detalles de instalación, despliegue en contenedores y cómo verificar que se está ejecutando este fork: [`docs/maintained/install.md`](./docs/maintained/install.md)
- Guía rápida de 5 minutos para creadores de plugins: [`docs/maintained/plugin-quickstart.md`](./docs/maintained/plugin-quickstart.md)
- Parámetros, valores de retorno y ejemplos de llamada de cada API: [`docs/maintained/api-reference.md`](./docs/maintained/api-reference.md)
- Restricciones de diseño de API y mecanismos de degradación: [`docs/maintained/api-contract.md`](./docs/maintained/api-contract.md)
- Por qué se estructura de esta forma: [`docs/maintained/design.md`](./docs/maintained/design.md)
- Qué ha cambiado respecto a upstream: [`CHANGELOG.md`](./CHANGELOG.md)
- Registro de cambios de core (SHA-256, verificable mediante script): [`maintained/installed_manifest.json`](./maintained/installed_manifest.json)

## Acerca de la terminología histórica

En etapas iniciales de este README, esta capa de interfaces se denominó «puerta trasera» (backdoor); actualmente se denomina de forma unificada «interfaz».

Los sitios espejo y la memoria caché de los motores de búsqueda aún pueden mostrar la redacción anterior, lo cual no representa la postura actual.

Estos módulos son API de Python públicas, documentadas y auditables línea por línea, y no contienen accesos ocultos para eludir la autenticación.

## Licencia

Este proyecto es de código abierto bajo la licencia AGPL-3.0-or-later, al igual que upstream. Consulte el archivo LICENSE para más detalles.

Este proyecto es una rama de mantenimiento independiente y no tiene relación de afiliación con los autores upstream.
