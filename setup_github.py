"""
One-shot GitHub setup. Reads GH_PAT from env, never logs it.
"""
import os, sys, json, base64, subprocess, urllib.request, urllib.error, ctypes, ctypes.util, tempfile

REPO_NAME = 'mtproto'
PRIVATE = True
SECRETS = {
    'API_ID': '35092539',
    'API_HASH': '5cb97629a5f64bb5db5eab5a6f25ab02',
    'BOT_TOKEN': '8860014485:AAGnO7X188pIewo8Z3Mfwssbu-eSG6JagNo',
    'CHANNEL_USERNAME': 'mtprotoactual',
}

PAT = os.environ.get('GH_PAT', '')
if not PAT:
    print('ERROR: GH_PAT env var is empty'); sys.exit(2)


def api(method, url, data=None):
    req = urllib.request.Request(url, method=method)
    req.add_header('Authorization', f'Bearer {PAT}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'mtproto-setup')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    body = json.dumps(data).encode('utf-8') if data is not None else None
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, body, timeout=30) as r:
            txt = r.read().decode('utf-8')
            return json.loads(txt) if txt else None
    except urllib.error.HTTPError as e:
        txt = e.read().decode('utf-8', errors='ignore')
        raise RuntimeError(f'{method} {url} -> {e.code}: {txt}')


def sealed_box_encrypt_b64(plaintext: str, pubkey_b64: str) -> str:
    """Sealed-box (anonymous) encryption using libsodium via ctypes."""
    pk = base64.b64decode(pubkey_b64)
    pt = plaintext.encode('utf-8')

    dll_path = None
    for cand in [
        os.path.join(os.environ.get('USERPROFILE', ''), r'scoop\apps\libsodium\current\x64\sodium.dll'),
        r'C:\Program Files\Libsodium\bin\sodium.dll',
        r'C:\Windows\System32\sodium.dll',
    ]:
        if os.path.exists(cand):
            dll_path = cand; break
    if not dll_path:
        raise RuntimeError('libsodium.dll not found. Install via: scoop install libsodium  OR  choco install libsodium')

    sodium = ctypes.CDLL(dll_path)
    sodium.sodium_init.restype = ctypes.c_int
    if sodium.sodium_init() < 0:
        raise RuntimeError('sodium_init failed')
    sodium.sodium_memzero.restype = None

    crypto_box_seal = sodium.crypto_box_seal
    crypto_box_seal.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulonglong, ctypes.c_char_p]
    crypto_box_seal.restype = ctypes.c_int

    crypto_box_sealbytes = sodium.crypto_box_sealbytes
    crypto_box_sealbytes.restype = ctypes.c_size_t

    sealbytes = crypto_box_sealbytes()
    ct = ctypes.create_string_buffer(sealbytes + len(pt))
    if crypto_box_seal(ct, pt, len(pt), pk) != 0:
        raise RuntimeError('crypto_box_seal failed')
    return base64.b64encode(ct.raw).decode('ascii')


def main():
    print('=== 1/4  Verify PAT ===')
    me = api('GET', 'https://api.github.com/user')
    user = me['login']
    print(f'  Authenticated as: {user}')

    print('=== 2/4  Create or reuse repo ===')
    try:
        repo = api('GET', f'https://api.github.com/repos/{user}/{REPO_NAME}')
        print(f'  Reusing existing: {repo["html_url"]}')
    except RuntimeError as e:
        if '404' in str(e):
            repo = api('POST', 'https://api.github.com/user/repos', {
                'name': REPO_NAME, 'private': PRIVATE, 'auto_init': False,
            })
            print(f'  Created: {repo["html_url"]}')
        else:
            raise

    print('=== 3/4  Push main branch ===')
    # ensure remote is clean
    subprocess.run(['git', 'remote', 'remove', 'origin'], capture_output=True)
    subprocess.run(['git', 'remote', 'add', 'origin', repo['clone_url']], check=True)
    print(f'  Remote: {repo["clone_url"]}')

    # push with token, embedded only in this command (not stored in config)
    auth_url = f'https://x-access-token:{PAT}@github.com/{user}/{REPO_NAME}.git'
    r = subprocess.run(['git', 'push', auth_url, 'main'], capture_output=True, text=True)
    if r.returncode != 0:
        print('STDOUT:', r.stdout)
        print('STDERR:', r.stderr)
        sys.exit(1)
    print('  Pushed.')

    print('=== 4/4  Add 4 repository secrets ===')
    pkr = api('GET', f'https://api.github.com/repos/{user}/{REPO_NAME}/actions/secrets/public-key')
    for name, val in SECRETS.items():
        enc = sealed_box_encrypt_b64(val, pkr['key'])
        api('PUT', f'https://api.github.com/repos/{user}/{REPO_NAME}/actions/secrets/{name}', {
            'encrypted_value': enc, 'key_id': pkr['key_id'],
        })
        print(f'  Secret set: {name}')

    print()
    print('=== DONE ===')
    print(f'Repo:    {repo["html_url"]}')
    print(f'Actions: {repo["html_url"]}/actions')
    print(f'Settings: {repo["html_url"]}/settings/secrets/actions')
    print()
    print('Next: open Actions tab -> enable workflow -> Run workflow once to test.')


if __name__ == '__main__':
    main()
