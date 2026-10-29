import base64
import re
from concurrent.futures import ThreadPoolExecutor
import pytest
from werkzeug.security import generate_password_hash
from app import create_app

@pytest.fixture
def env(tmp_path):
    app = create_app({'TESTING': True, 'ROOT':str(tmp_path/'files'), 'STATE':str(tmp_path/'state'),
                     'USERS':{'tester':generate_password_hash('secret', method='pbkdf2:sha256:1000')}})
    client = app.test_client()
    auth = {'Authorization':'Basic '+base64.b64encode(b'tester:secret').decode()}
    page = client.get('/', headers=auth)
    token = re.search(r'name="csrf-token" content="([^"]+)"', page.text)[1]
    headers = {**auth, 'X-CSRF-Token':token}
    return app, client, headers, tmp_path

def save(c,h,name='test.md',content='original',revision=None):
    return c.post('/api/files/'+name, json={'content':content,'revision':revision},headers=h)

def test_auth_and_csrf(env):
    app,c,h,p=env
    assert c.get('/api/files').status_code == 401
    assert c.post('/api/files/a.md',json={'content':'x'},headers={'Authorization':h['Authorization']}).status_code == 403
    assert c.get('/api/files',headers=h).status_code == 200

def test_lifecycle_and_versions(env):
    app,c,h,p=env
    r=save(c,h); assert r.status_code == 200
    old=r.json['revision']
    assert save(c,h,content='overwrite').status_code == 409
    r=save(c,h,content='new',revision=old); assert r.status_code == 200
    assert save(c,h,content='stale',revision=old).status_code == 409
    rev=r.json['revision']
    r=c.patch('/api/files/test.md',json={'filename':'renamed.md','revision':rev},headers=h)
    assert r.status_code == 200
    assert c.get('/api/files/test.md',headers=h).status_code == 404
    r=c.delete('/api/files/renamed.md',json={'revision':rev},headers=h); assert r.status_code == 200
    key=r.json['archive_id']
    assert c.get('/api/files/renamed.md',headers=h).status_code == 404
    assert c.post(f'/api/archive/{key}/restore',json={'filename':'restored.md'},headers=h).status_code == 200
    assert c.post(f'/api/archive/{key}/restore',json={'filename':'restored.md'},headers=h).status_code == 409
    entries=c.get('/api/archive',headers=h).json
    assert {e['kind'] for e in entries} == {'version','deleted'}
    version=next(e for e in entries if e['kind']=='version')
    c.post(f"/api/archive/{version['id']}/restore",json={'filename':'old.md'},headers=h)
    assert c.get('/api/files/old.md',headers=h).json['content']=='original'

@pytest.mark.parametrize('name',['..hidden.md','bad%5Cfile.md','file.txt','%00.md','%20space.md'])
def test_bad_names(env,name):
    app,c,h,p=env
    assert save(c,h,name).status_code == 400

def test_symlinks(env):
    app,c,h,p=env
    outside=p/'private'; outside.write_text('private')
    (p/'files'/'link.md').symlink_to(outside)
    assert c.get('/api/files/link.md',headers=h).status_code==400
    assert save(c,h,'link.md').status_code==400
    assert c.get('/api/files',headers=h).json==[]
    assert outside.read_text()=='private'

def test_encoding_and_special_names(env):
    app,c,h,p=env
    (p/'files'/'UTF.MD').write_bytes('área'.encode('utf-16'))
    assert c.get('/api/files/UTF.MD',headers=h).json['content']=='área'
    (p/'files'/'bom.md').write_bytes(b'\xef\xbb\xbfhello\r\n')
    assert c.get('/api/files/bom.md',headers=h).json['content']=='hello\r\n'
    assert save(c,h,'Espa%C3%B1a%20%23%201.md').status_code==200
    assert c.get('/api/files/Espa%C3%B1a%20%23%201.md',headers=h).status_code==200
    (p/'files'/'bad.md').write_bytes(b'\x80')
    assert c.get('/api/files/bad.md',headers=h).status_code==422

def test_malformed_and_limits(env):
    app,c,h,p=env
    for data in (None, [], {'content':5}):
        assert c.post('/api/files/a.md',json=data,headers=h).status_code==400
    assert save(c,h,content='x'*(2097152+1)).status_code==413

def test_render(env):
    app,c,h,p=env
    text='''# Heading

| A | B |
| - | - |
| 1 | 2 |

- [x] Done

~deleted~~ and $a_1^2$.

$$
\\frac{a}{b}
$$

Footnote[^1]

[^1]: Note

```mermaid
flowchart TD
A-->B
```

<details><summary>Open</summary>Content</details>
<script>alert(1)</script><img src="https://example.com/x" onerror="alert(1)">
<a href="javascript:alert(1)">bad</a>
'''
    r=c.post('/api/render',json={'content':text},headers=h)
    assert r.status_code==200
    out=r.json['html']
    for expected in ['<table>','checkbox','<s>deleted</s>','math-tex','a_1^2','\\frac{a}{b}','footnote','language-mermaid','<details>']:
        assert expected in out
    for forbidden in ['<script','onerror','javascript:']:
        assert forbidden not in out

def test_simultaneous_create(env):
    app,c,h,p=env
    def write(n):
        with app.test_client() as client:
            return save(client,h,content=str(n)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(write,[1,2]))
    assert sorted(results)==[200,409]

def test_rename_conflict_and_deleted_save(env):
    app,c,h,p=env
    rev=save(c,h).json['revision']
    save(c,h,'other.md')
    assert c.patch('/api/files/test.md',json={'filename':'other.md','revision':rev},headers=h).status_code==409
    c.delete('/api/files/test.md',json={'revision':rev},headers=h)
    assert save(c,h,revision=rev).status_code==409
