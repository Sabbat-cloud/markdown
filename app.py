"""Editor Markdown para Debian/Linux. Ejecutar con python app.py (Waitress)."""
import fcntl
import hashlib
import html
import json
import logging
import os
import re
import stat
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from logging.handlers import RotatingFileHandler

import bleach
from flask import Flask, Response, abort, jsonify, render_template, request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash

BASE = Path(__file__).resolve().parent
LIMIT = 2 * 1024 * 1024


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        ROOT=str(BASE / 'markdown_files'),
        STATE=str(BASE / 'instance'),
        MAX_CONTENT_LENGTH=LIMIT * 6 + 65536,
        USERS={k[len('AUTH_USER_'):]: v for k, v in os.environ.items() if k.startswith('AUTH_USER_')},
    )
    app.config['ROOT'] = os.environ.get('MARKDOWN_FOLDER', app.config['ROOT'])
    app.config['STATE'] = os.environ.get('MARKDOWN_STATE', app.config['STATE'])
    if config:
        app.config.update(config)
    root = Path(app.config['ROOT']).resolve()
    state = Path(app.config['STATE']).resolve()
    root.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    archive = state / 'archive'
    archive.mkdir(exist_ok=True, mode=0o700)
    secret = state / 'secret.key'
    # La inicialización se serializa también entre procesos.
    with open(state / 'init.lock', 'a') as init_lock:
        fcntl.flock(init_lock, fcntl.LOCK_EX)
        if not secret.exists():
            fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(os.urandom(32))
        signer = URLSafeTimedSerializer(secret.read_bytes(), salt='markdown-csrf-v2')
    try:
        handler = RotatingFileHandler(os.environ.get('LOG_FILE', '/var/log/markdown-editor.log'),
                                      maxBytes=1_000_000, backupCount=3)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        handler.setLevel(logging.WARNING)
        app.logger.addHandler(handler)
    except OSError:
        app.logger.warning('No se pudo abrir LOG_FILE; se utilizará stderr/journal.')
    if not app.config['USERS']:
        app.logger.warning('Sin AUTH_USER_*: todos los accesos serán rechazados.')

    @contextmanager
    def locked():
        with open(state / 'files.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def fail(message, code=400):
        abort(code, description=message)

    def filename(value):
        if not isinstance(value, str):
            fail('Nombre no válido.')
        if (not value or value != value.strip() or value.startswith('.') or
                any(c in value for c in '/\\') or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            fail('Usa un nombre de archivo sin rutas ni caracteres de control.')
        if not value.lower().endswith(('.md', '.markdown')):
            fail('La extensión debe ser .md o .markdown.')
        if len(value.encode('utf-8')) > 200:
            fail('Nombre demasiado largo.')
        return value

    def read_bytes(path):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            fail('El archivo no existe.', 404)
        except OSError:
            fail('No se puede abrir el archivo o es un enlace simbólico.', 400)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                fail('No es un archivo normal.')
            if info.st_size > LIMIT:
                fail('El límite por documento es 2 MiB.', 413)
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            fail('El límite por documento es 2 MiB.', 413)
        return raw

    def revision(raw):
        return hashlib.sha256(raw).hexdigest()

    def decode(raw):
        try:
            if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
                return raw.decode('utf-16'), 'UTF-16 (se guardará como UTF-8)'
            return raw.decode('utf-8-sig'), 'UTF-8'
        except UnicodeError:
            fail('Codificación no compatible. Convierte el documento a UTF-8.', 422)

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            fail('Se esperaba un objeto JSON.')
        return data

    def content(data):
        value = data.get('content')
        if not isinstance(value, str):
            fail('El contenido debe ser texto.')
        try:
            raw = value.encode('utf-8')
        except UnicodeError:
            fail('Texto Unicode no válido.')
        if len(raw) > LIMIT:
            fail('El límite por documento es 2 MiB.', 413)
        return raw

    def check_revision(path, expected):
        raw = read_bytes(path)
        if not isinstance(expected, str) or revision(raw) != expected:
            fail('El archivo cambió en el servidor. Descarga tu borrador antes de volver a abrirlo.', 409)
        return raw

    def atomic_write(path, raw):
        fd, temp = tempfile.mkstemp(prefix='.write-', dir=root)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def snapshot(name, raw, kind):
        key = uuid.uuid4().hex
        temp = archive / ('.' + key)
        temp.mkdir(mode=0o700)
        (temp / 'content').write_bytes(raw)
        (temp / 'meta.json').write_text(json.dumps(dict(id=key, filename=name, kind=kind,
            date=datetime.now(timezone.utc).isoformat(), size=len(raw)), ensure_ascii=False), encoding='utf-8')
        os.rename(temp, archive / key)
        return key

    def protected(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            ips = [i.strip() for i in os.environ.get('AUTHORIZED_IPS', '').split(',') if i.strip()]
            if ips and request.remote_addr not in ips:
                fail('IP no autorizada.', 403)
            auth = request.authorization
            valid = False
            if auth and auth.type.lower() == 'basic' and auth.username in app.config['USERS']:
                try:
                    valid = check_password_hash(app.config['USERS'][auth.username], auth.password or '')
                except (ValueError, TypeError):
                    pass
            if not valid:
                # No incluir nombres de usuario controlados por el cliente en los logs.
                app.logger.warning("Failed login attempt for user '(redacted)' from IP '%s'", request.remote_addr)
                return Response('Acceso no autorizado.', 401, {'WWW-Authenticate': 'Basic realm="Markdown Editor", charset="UTF-8"'})
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                try:
                    user = signer.loads(request.headers.get('X-CSRF-Token', ''), max_age=43200)
                    if user != auth.username:
                        raise BadSignature('Usuario incorrecto')
                except (BadSignature, SignatureExpired):
                    fail('Sesión de edición caducada. Descarga el borrador y recarga la página.', 403)
            return f(*args, **kwargs)
        return wrapper

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net; img-src 'self' https: data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(Exception)
    def unexpected(error):
        app.logger.exception('Error interno')
        return jsonify(error='Error interno. Consulta el registro del servidor.'), 500

    @app.get('/')
    @protected
    def index():
        return render_template('index.html', csrf=signer.dumps(request.authorization.username))

    @app.get('/api/files')
    @protected
    def files():
        with locked():
            result = []
            for path in root.iterdir():
                if path.is_symlink() or not path.is_file() or path.name.startswith('.'):
                    continue
                if path.suffix.lower() in ('.md', '.markdown'):
                    info = path.stat()
                    result.append(dict(filename=path.name, size=info.st_size, modified=info.st_mtime))
            return jsonify(sorted(result, key=lambda x: x['filename'].casefold()))

    @app.route('/api/files/<string:name>', methods=['GET', 'POST', 'DELETE', 'PATCH'])
    @protected
    def file_action(name):
        name = filename(name)
        path = root / name
        with locked():
            if request.method == 'GET':
                raw = read_bytes(path)
                value, encoding = decode(raw)
                return jsonify(filename=name, content=value, revision=revision(raw), encoding=encoding)
            data = body()
            if request.method == 'POST':
                raw = content(data)
                if os.path.lexists(path):
                    old = check_revision(path, data.get('revision'))
                    if old != raw:
                        snapshot(name, old, 'version')
                elif data.get('revision') is not None:
                    fail('El archivo fue eliminado o renombrado. Usa Guardar como.', 409)
                atomic_write(path, raw)
                return jsonify(filename=name, revision=revision(raw))
            old = check_revision(path, data.get('revision'))
            if request.method == 'DELETE':
                key = snapshot(name, old, 'deleted')
                path.unlink()
                return jsonify(success=True, archive_id=key)
            target = filename(data.get('filename'))
            dest = root / target
            if target == name:
                return jsonify(filename=name, revision=revision(old))
            if os.path.lexists(dest):
                fail('Ya existe un archivo con ese nombre.', 409)
            # link no reemplaza un destino creado simultáneamente.
            os.link(path, dest, follow_symlinks=False)
            path.unlink()
            return jsonify(filename=target, revision=revision(old))

    @app.get('/api/archive')
    @protected
    def history():
        with locked():
            entries = [json.loads((p / 'meta.json').read_text(encoding='utf-8'))
                       for p in archive.iterdir() if re.fullmatch(r'[a-f0-9]{32}', p.name) and p.is_dir()]
        return jsonify(sorted(entries, key=lambda x: x['date'], reverse=True))

    @app.post('/api/archive/<string:key>/restore')
    @protected
    def restore(key):
        if not re.fullmatch(r'[a-f0-9]{32}', key):
            fail('Identificador no válido.')
        data = body()
        with locked():
            name = filename(data.get('filename'))
            if os.path.lexists(root / name):
                fail('El destino ya existe. Elige otro nombre.', 409)
            raw = read_bytes(archive / key / 'content')
            atomic_write(root / name, raw)
        return jsonify(filename=name, revision=revision(raw))

    @app.post('/api/render')
    @protected
    def render():
        source = content(body()).decode('utf-8')
        # Cada petición usa sus propias instancias (Waitress tiene varios hilos).
        md = MarkdownIt('commonmark', {'html': True, 'breaks': False}).enable(['table', 'strikethrough'])
        md.use(footnote_plugin).use(tasklists_plugin).use(dollarmath_plugin)
        def math_rule(tokens, idx, options, env):
            token = tokens[idx]
            tag = 'div' if token.type.startswith('math_block') else 'span'
            return f'<{tag} class="math-tex">{html.escape(token.content)}</{tag}>'
        for rule in ('math_inline', 'math_inline_double', 'math_block', 'math_block_label'):
            md.renderer.rules[rule] = math_rule
        tags = {'p','br','hr','h1','h2','h3','h4','h5','h6','ul','ol','li','a','strong','em','s','del',
                'blockquote','pre','code','table','thead','tbody','tr','th','td','img','sup','sub',
                'details','summary','div','span','section','input'}
        def attrs(tag, name, value):
            if name in ('title', 'alt'):
                return True
            if tag == 'a' and name == 'href':
                return True
            if tag == 'img' and name == 'src':
                return value.startswith('https://')
            if name == 'id':
                return value.startswith(('fn', 'fnref'))
            if name == 'class':
                return all(v.startswith(('language-', 'footnote', 'task-list', 'contains-task-list'))
                           or v == 'math-tex' for v in value.split())
            if tag == 'input':
                return (name == 'type' and value == 'checkbox') or name in ('checked', 'disabled')
            return tag == 'ol' and name == 'start'
        clean = bleach.clean(md.render(source), tags=tags, attributes=attrs,
                             protocols={'http', 'https', 'mailto'}, strip=True)
        return jsonify(html=clean)

    return app


app = create_app()
if __name__ == '__main__':
    from waitress import serve
    serve(app, host=os.environ.get('HOST', '0.0.0.0'), port=int(os.environ.get('PORT', '3555')),
          max_request_body_size=LIMIT * 6 + 65536)
