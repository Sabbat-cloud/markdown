# Sabbat Markdown Editor

Español · [English](README.md)

Aplicación web Flask + Waitress para editar documentos Markdown, con vista previa, gestión compartida de archivos, borrado recuperable y versiones anteriores. El acceso está protegido mediante autenticación HTTP Basic y hashes de contraseña de Werkzeug.

El editor trabaja directamente con el código Markdown. **No es un editor WYSIWYG**: los botones de formato insertan sintaxis Markdown y la vista previa es de solo lectura. Así se evita convertir el contenido renderizado de nuevo a Markdown al guardar.

## Funcionalidades

- Crear, abrir, guardar, guardar como y renombrar documentos `.md` / `.markdown`.
- Borrar archivos de la carpeta de documentos y recuperarlos desde la papelera.
- Conservar automáticamente el contenido anterior al sobrescribir un documento modificado.
- Restaurar una copia archivada sin sobrescribir un archivo existente.
- Detectar conflictos de guardado entre pestañas mediante revisiones de los archivos.
- Importar documentos locales, descargar el texto actual e imprimir la vista previa o guardarla como PDF desde el navegador.
- Barra de formato, búsqueda y reemplazo literal, tema claro/oscuro y vistas dividida/editor/lectura.
- Avisos de cambios sin guardar, contador de palabras/caracteres/líneas y Ctrl+S / Cmd+S.
- Recuperación del último documento de la pestaña mediante `sessionStorage`.
- Tablas, listas de tareas, tachado, notas al pie, resaltado de código, fórmulas KaTeX y diagramas Mermaid.
- HTML básico saneado, protección CSRF, validación de nombres y rechazo de enlaces simbólicos.

Todos los usuarios autorizados comparten los mismos documentos, papelera e historial. No hay permisos por documento ni edición colaborativa en tiempo real.

## Requisitos

- Linux, preferiblemente Debian o Ubuntu. El bloqueo de archivos utiliza `fcntl`.
- Python **3.10 o posterior**, `pip` y `venv`.
- Dependencias incluidas en `requirements.txt`.
- Navegador moderno con JavaScript habilitado.
- Acceso del navegador a jsDelivr para KaTeX, Mermaid, resaltado de código y sus estilos/fuentes.
- HTTPS para acceder desde una red no confiable, normalmente mediante el proxy inverso Nginx existente.

El Markdown básico se renderiza en el servidor. Si los recursos del CDN no están disponibles, se puede seguir editando, pero algunas funciones de visualización mostrarán el texto original.

## Estructura del proyecto

```text
markdown/
├── app.py
├── requirements.txt
├── README.md
├── README.ES.md
├── ejemplo.md
├── templates/
│   └── index.html
├── static/
│   ├── app.js
│   └── style.css
├── tests/
│   └── test_app.py
├── markdown_files/       # Creación automática: documentos
└── instance/             # Creación automática: estado y archivo de versiones
```

No publiques `instance/` como directorio estático ni lo subas a un repositorio. Incluye ambas carpetas de datos en tus copias de seguridad.

## Instalación

Los ejemplos utilizan la cuenta Linux **`sabbat`** y la ruta **`/home/sabbat/markdown`**. Adapta ambos valores si corresponde. Ejecuta la aplicación con ese usuario, no como root.

### 1. Instalar dependencias del sistema y copiar la aplicación

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip unzip
mkdir -p ~/markdown
cd ~/markdown
```

Copia `app.py`, `requirements.txt`, `templates/` y `static/` dentro de este directorio. Copia también la documentación, el ejemplo y las pruebas si están incluidos. Al actualizar, conserva tu carpeta `markdown_files/` existente.

### 2. Crear el entorno virtual

```bash
cd ~/markdown
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

### 3. Generar un hash de contraseña

No hace falta un archivo `hash_generator.py` independiente. Este comando solicita la contraseña sin incluirla en los argumentos del proceso ni en el historial de la shell:

```bash
python -c 'from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass("Contraseña: ")))' 
```

Copia la salida completa, incluidos los caracteres `$`. Guarda hashes, no contraseñas en texto plano. Puedes reutilizar los hashes Werkzeug compatibles que ya utilizabas.

### 4. Configurar el entorno del servicio

```bash
sudo install -d -m 750 /etc/markdown
sudo touch /etc/markdown/markdown.conf
sudo chown root:root /etc/markdown/markdown.conf
sudo chmod 600 /etc/markdown/markdown.conf
sudo nano /etc/markdown/markdown.conf
```

Contenido de ejemplo; sustituye el marcador por tu hash completo:

```ini
AUTH_USER_admin=PEGA_AQUI_EL_HASH_WERKZEUG_COMPLETO
MARKDOWN_FOLDER=/home/sabbat/markdown/markdown_files
MARKDOWN_STATE=/home/sabbat/markdown/instance
HOST=127.0.0.1
PORT=3555
LOG_FILE=/var/log/markdown/markdown-editor.log
```

Añade `AUTH_USER_editor1=...` para otro usuario. El sufijo es el nombre de inicio de sesión y distingue mayúsculas y minúsculas. Si no hay usuarios configurados, se rechazan todos los accesos.

Este archivo lo lee systemd: utiliza `CLAVE=VALOR`, sin `export`. Aquí puedes pegar el hash sin comillas; `$` no se expande como en una shell. **No cargues este archivo sin comillas mediante `source`.** En comandos de shell, encierra los hashes entre comillas simples. Reinicia el servicio después de cambiar las credenciales.

`HOST=127.0.0.1` sirve para un proxy inverso local o un túnel SSH. Mantén la dirección que necesite tu despliegue actual; el valor predeterminado de la aplicación es `0.0.0.0`.

## Ejecutar la aplicación

### Prueba manual

El archivo de entorno anterior no se carga automáticamente al ejecutar Python manualmente. En una terminal con el entorno virtual activado:

```bash
cd ~/markdown
mkdir -p instance
export AUTH_USER_admin='PEGA_AQUI_EL_HASH_WERKZEUG_COMPLETO'
export HOST=127.0.0.1
export LOG_FILE="$PWD/instance/markdown-editor.log"
python app.py
```

Accede a `http://127.0.0.1:3555` desde el servidor o mediante un túnel SSH. Si el servidor es remoto, ejecuta en tu ordenador:

```bash
ssh -L 3555:127.0.0.1:3555 sabbat@TU_SERVIDOR
```

Después abre `http://127.0.0.1:3555` localmente. Detén el proceso manual antes de iniciar systemd en el mismo puerto.

### Servicio systemd

Si ya tienes un servicio funcionando, adapta ese servicio en lugar de crear otro que utilice el puerto 3555. El nombre utilizado en el ejemplo es `markdown-editor.service`.

```bash
sudo nano /etc/systemd/system/markdown-editor.service
```

```ini
[Unit]
Description=Sabbat Markdown Editor
After=network.target

[Service]
Type=simple
User=sabbat
Group=www-data
WorkingDirectory=/home/sabbat/markdown
EnvironmentFile=/etc/markdown/markdown.conf
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/sabbat/markdown/venv/bin/python /home/sabbat/markdown/app.py
Restart=on-failure
RestartSec=5
UMask=0077
LogsDirectory=markdown
LogsDirectoryMode=0750
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

El usuario del servicio necesita permisos de escritura en `markdown_files/` e `instance/`. `LogsDirectory=markdown` proporciona un directorio de logs dedicado y escribible; esto permite que el manejador de rotación cree y renombre las copias de los registros. Dar permisos únicamente a un archivo situado en `/var/log` no basta para rotar si no se puede escribir en el directorio padre.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now markdown-editor.service
sudo systemctl status markdown-editor.service
```

Si el servicio ya estaba ejecutándose, reinícialo expresamente después de cambiar su configuración:

```bash
sudo systemctl restart markdown-editor.service
```

### Gestión del servicio

```bash
sudo systemctl status markdown-editor.service
sudo journalctl -u markdown-editor.service -f
sudo systemctl restart markdown-editor.service
sudo systemctl stop markdown-editor.service
```

## Variables de entorno

| Variable | Valor predeterminado de la aplicación | Función |
| --- | --- | --- |
| `AUTH_USER_nombre` | Ninguno | Hash Werkzeug del usuario `nombre` |
| `MARKDOWN_FOLDER` | `markdown_files` junto a `app.py` | Carpeta de documentos |
| `MARKDOWN_STATE` | `instance` junto a `app.py` | Clave, bloqueos y versiones archivadas |
| `HOST` | `0.0.0.0` | Dirección de escucha de Waitress |
| `PORT` | `3555` | Puerto de Waitress |
| `LOG_FILE` | `/var/log/markdown-editor.log` | Archivo de log con rotación |
| `AUTHORIZED_IPS` | Vacío | Lista opcional de IP exactas, separadas por comas |

El ejemplo del servicio cambia expresamente `HOST` y `LOG_FILE`. Utiliza rutas absolutas para los datos. Si la lista de IP está vacía, cualquier IP puede acceder con credenciales válidas. Si falla la apertura del log, la aplicación lo comunica por stderr/journal. Si el fallo aparece al rotar después de abrir el archivo, hay que corregir los permisos.

## Edición y recuperación

1. Selecciona un documento o crea uno nuevo.
2. Edita el texto original; la vista previa se actualiza tras una breve pausa.
3. Guarda con el botón o Ctrl+S / Cmd+S. Utiliza **Guardar como** para crear otro archivo.
4. Guarda los cambios antes de renombrar o borrar el documento.
5. Abre **Papelera / versiones** para restaurar un archivo borrado o un contenido anterior. Elige otro nombre si el destino ya existe.

La interfaz actual utiliza etiquetas en español, incluidas **Guardar**, **Guardar como** y **Papelera / versiones**.

Se crea una copia archivada únicamente al sobrescribir contenido diferente o borrar un documento existente. No se guarda una versión de cada pulsación. Las copias no caducan automáticamente y no hay botón de borrado permanente; revisa el espacio disponible.

El borrador de la pestaña no es un autoguardado en el servidor. Después de recargar, pulsa **Recuperar borrador** antes de abrir otro archivo. Solo se conserva el último borrador de esa pestaña y cerrarla puede eliminarlo. Las políticas del navegador o sus límites de almacenamiento también pueden impedir la recuperación.

Si aparece un conflicto de guardado, descarga tu borrador, vuelve a abrir la versión del servidor y combina los cambios. Los tokens CSRF caducan a las 12 horas; si aparece el aviso, descarga el borrador antes de recargar.

## Compatibilidad Markdown y límites

- Archivos `.md` / `.markdown`, con extensiones sin distinción entre mayúsculas y minúsculas; admite espacios y nombres Unicode. Sin subcarpetas.
- Tamaño máximo por documento: **2 MiB**. Los archivos mayores pueden aparecer en la lista, pero no se pueden abrir ni modificar desde el editor.
- Codificación: UTF-8 con/sin BOM o UTF-16 con BOM. Otras codificaciones requieren conversión.
- Se guarda en UTF-8. El navegador puede normalizar CRLF a LF y se eliminan los BOM; no se garantiza la conservación exacta de los bytes.
- Fórmulas: `$...$` en línea y bloques `$$...$$`. No están implementados `\(...\)` ni `\[...\]`.
- Diagramas: bloques de código delimitados por tres acentos graves y con lenguaje `mermaid`.
- El HTML básico se sanea. No se admiten scripts, manejadores de eventos, iframes ni estilos arbitrarios.
- Las imágenes necesitan una URL HTTPS. No hay subida de imágenes ni publicación de adjuntos locales.
- Los enlaces Markdown del mismo origen abren documentos por su nombre de archivo; no se resuelven rutas anidadas.
- No admite MDX, componentes JavaScript arbitrarios, sintaxis propia de Obsidian ni todos los plugins existentes.
- Las versiones del CDN son explícitas; una instalación completamente desconectada necesita servir esos recursos localmente y adaptar la plantilla/CSP.

Importa `ejemplo.md` para comprobar los formatos admitidos en tu navegador. El despliegue suministrado utiliza la raíz de un host; publicarlo bajo un prefijo de URL necesita configuración adicional de Flask/proxy.

## Logs y Fail2Ban opcional

La aplicación registra los fallos de autenticación, incluidas las peticiones sin credenciales. Por ello, el desafío inicial de HTTP Basic puede generar una entrada incluso para un visitante legítimo. Ajusta los umbrales teniendo esto en cuenta.

El manejador rota aproximadamente a 1 MB y conserva tres archivos anteriores. Con el servicio mostrado, el log se encuentra en `/var/log/markdown/markdown-editor.log`.

### Limitación con proxy inverso

**La aplicación registra `request.remote_addr`; no confía automáticamente en `X-Forwarded-For`.** Detrás de un Nginx local, normalmente verá `127.0.0.1`, no la IP del visitante. No habilites la jail de acceso directo que aparece a continuación sobre esos registros. Bloquear el proxy no identificaría al atacante y podría interrumpir el acceso.

Si utilizas Nginx, revisa por separado una configuración basada en sus logs/autenticación o configura expresamente la confianza en el proxy después de restringir el acceso al backend. Una cabecera `X-Forwarded-For` arbitraria no demuestra la identidad del cliente. `AUTHORIZED_IPS` tiene la misma limitación con el proxy.

### Ejemplo de jail para acceso directo

Utiliza este ejemplo solo cuando los registros contengan la IP real del cliente y el tráfico que quieras proteger acceda realmente por el puerto 3555. No es la jail adecuada para peticiones que llegan mediante HTTPS al puerto 443.

```bash
sudo apt install fail2ban
sudo nano /etc/fail2ban/filter.d/markdown-editor.conf
```

```ini
[Definition]
failregex = ^\s*- app - WARNING - Failed login attempt for user '\(redacted\)' from IP '<HOST>'\s*$
ignoreregex =
```

El filtro corresponde al logger `app` de la aplicación después de que Fail2Ban elimine la fecha. Compruébalo contra el formato real de tu log:

```bash
sudo fail2ban-regex /var/log/markdown/markdown-editor.log /etc/fail2ban/filter.d/markdown-editor.conf
```

Después crea `/etc/fail2ban/jail.d/markdown-editor.local`:

```ini
[markdown-editor]
enabled  = true
backend  = polling
port     = 3555
filter   = markdown-editor
logpath  = /var/log/markdown/markdown-editor.log
usedns   = no
maxretry = 10
findtime = 600
bantime  = 600
```

Este ejemplo bloquea durante 10 minutos después de 10 fallos coincidentes en 10 minutos. Revisa el umbral y la acción del firewall según tu entorno.

```bash
sudo fail2ban-client -t
sudo systemctl restart fail2ban
sudo fail2ban-client status markdown-editor
```

## Actualizaciones y copias de seguridad

Si solo actualizas la documentación, sustituye `README.md` y `README.ES.md`; **no hace falta reiniciar el servicio**.

Para actualizar la aplicación, detén primero el servicio real y respalda la instalación:

```bash
sudo systemctl stop markdown-editor.service
cd ~
tar --exclude='markdown/venv' --exclude='markdown/.venv' \
    --exclude='markdown/__pycache__' \
    -czf "markdown-backup-$(date +%Y%m%d-%H%M%S).tar.gz" markdown
```

Si utilizas rutas de datos personalizadas, respáldalas por separado. Guarda también `/etc/markdown/markdown.conf` y tu unidad systemd con las restricciones de acceso adecuadas.

Sustituye los archivos de aplicación, conserva `markdown_files/` e `instance/`, instala las dependencias actualizadas y reinicia:

```bash
cd ~/markdown
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
sudo systemctl restart markdown-editor.service
```

Recarga el navegador con Ctrl+F5. Recupera una copia de seguridad si la actualización falla.

El contenido archivado está en `instance/archive/<id>/content`, con el nombre original y la fecha en `meta.json`. Esto permite recuperarlo manualmente, pero las copias locales no sustituyen los backups externos. Los bloqueos coordinan los procesos de esta aplicación que comparten el directorio de estado; no coordinan otros editores externos. Utiliza un sistema de archivos local.

## Pruebas y resolución de problemas

Desde el directorio del proyecto y con el entorno virtual activado:

```bash
python -m pip install pytest
python -m pytest -q
```

Las pruebas del backend cubren autenticación, CSRF, creación simultánea, conflictos de guardado/renombrado, restauración de papelera/versiones, rutas inválidas, enlaces simbólicos, codificaciones, límites de tamaño y renderizado saneado.

| Síntoma | Comprobación |
| --- | --- |
| Se rechaza el acceso | Hash completo, usuario exacto, variables `AUTH_USER_*` cargadas y reinicio del servicio |
| No aparecen archivos | `MARKDOWN_FOLDER`, ubicación real de los datos y permisos del usuario del servicio |
| HTTP 409 | Cambió el contenido del servidor o ya existe el destino; recupera/renombra el borrador |
| HTTP 403 al guardar | Token CSRF caducado o restricción de IP; descarga el borrador antes de recargar |
| HTTP 413 | Documento de más de 2 MiB o petición superior al límite del proxy |
| Fórmula/diagrama mostrado como texto | Sintaxis, acceso al CDN y consola del navegador |
| Error al rotar logs | Permisos de escritura del directorio, no solo del archivo |
| Puerto ocupado | Otro proceso manual o servicio está escuchando en 3555 |

## Referencias técnicas

- [Entorno de los servicios systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)
- [Recomendaciones para filtros Fail2Ban](https://github.com/fail2ban/fail2ban/blob/master/FILTERS)
- [Comprobación de expresiones Fail2Ban](https://github.com/fail2ban/fail2ban/blob/master/man/fail2ban-regex.1)
- [Seguridad de markdown-it-py](https://markdown-it-py.readthedocs.io/en/latest/security.html)
- [Configuración de Mermaid](https://mermaid.js.org/config/usage)
- [Opciones de KaTeX](https://katex.org/docs/options)

