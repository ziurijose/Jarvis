"""JARVIS's long-term memory search. Every exchange is written down, so Claude can forget a
conversation when it ends and still look it up ("what were we just talking about?", "what was
that restaurant I mentioned?").

A search reads the Obsidian vault itself: every fact in Memory.md, every exchange in the day
notes, and the user's own notes. So it finds things as they are now in Obsidian, edits included,
and nothing is ever too old to find. conversations.jsonl keeps exact conversation boundaries,
for "the last conversation".

Search is by meaning, with a small on-device model (all-MiniLM-L6-v2, about 23 MB, run with
onnxruntime and tokenizers, which the voice and wake word already need). Until the model is
there, or if it can't load, search matches keywords instead.
"""
import datetime
import hashlib
import json
import os
import re
import threading

import vault

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, 'conversations.jsonl')
INDEX_PATH = os.path.join(HERE, 'recall_index.npz')
OLD_INDEX_PATH = os.path.join(HERE, 'recall_index.npy')  # the index before search read the vault
MODEL_DIR = os.path.join(HERE, 'models', 'recall')
MODEL_URL = 'https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/'
MODEL_FILES = {'model.onnx': 'onnx/model_quantized.onnx', 'tokenizer.json': 'tokenizer.json'}
DIMENSIONS = 384
MIN_MODEL_BYTES = 100_000  # a real model is megabytes; an error page is a few KB
MAX_CHARS = 1500  # what one recall may add to Claude's context
BEST = 8
KEYWORD_WEIGHT = 0.1  # added to meaning similarity (0 to 1), so exact names and numbers still win
PIECE_CHARS = 600  # a longer paragraph is split, so each piece stays about one thought
WORD = re.compile(r"[a-z0-9']+")
DAY_NOTE = re.compile(r'^(\d{4}-\d{2}-\d{2})\.md$')

_lock = threading.RLock()
_current = None        # this conversation's number
_model = None          # (onnxruntime session, tokenizer) once loaded
_piece_vectors = {}    # sha1 of a piece's text -> its vector (numpy), saved in INDEX_PATH
_parsed = {}           # note path -> (modified time, its pieces), so unchanged notes aren't re-read


def use_folder(folder, model_dir=None):
    """Keeps conversations in another folder (tests use a temporary one)."""
    global LOG_PATH, INDEX_PATH, OLD_INDEX_PATH, MODEL_DIR, _current, _model
    with _lock:
        LOG_PATH = os.path.join(folder, 'conversations.jsonl')
        INDEX_PATH = os.path.join(folder, 'recall_index.npz')
        OLD_INDEX_PATH = os.path.join(folder, 'recall_index.npy')
        MODEL_DIR = model_dir or os.path.join(folder, 'models', 'recall')
        _current, _model = None, None
        _piece_vectors.clear()
        _parsed.clear()


def _lines():
    """Every exchange written down, oldest first. Lines that can't be read are skipped."""
    try:
        with open(LOG_PATH, encoding='utf-8') as f:
            raw = f.readlines()
    except OSError:
        return []
    items = []
    for line in raw:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and isinstance(item.get('conv'), int):
            items.append(item)
    return items


def start_conversation():
    """Numbers a new conversation: one more than the last one written down."""
    global _current
    with _lock:
        last = max((item['conv'] for item in _lines()), default=0)
        _current = max(last, _current or 0) + 1
        return _current


def record(conv, you, jarvis):
    """Writes one exchange down. Never raises: an answer must not fail because of this."""
    item = {'t': datetime.datetime.now().isoformat(timespec='seconds'), 'conv': conv,
            'you': you.strip(), 'jarvis': jarvis.strip()}
    try:
        with _lock:
            with open(LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
    except Exception as error:
        print(f'Could not write the conversation down: {error}')
    vault.add_exchange(item['you'], item['jarvis'])  # what search reads (never raises)


def forget(about):
    """Removes every exchange that mentions about (any capitals), and returns how many went.
    Never raises, like record."""
    needle = about.strip().lower()
    if not needle:
        return 0
    vault.forget_exchanges(about)
    try:
        with _lock:
            items = _lines()
            kept = [item for item in items if needle not in _text(item).lower()]
            removed = len(items) - len(kept)
            if removed:
                part = LOG_PATH + '.part'
                with open(part, 'w', encoding='utf-8') as f:
                    for item in kept:
                        f.write(json.dumps(item, ensure_ascii=False) + '\n')
                os.replace(part, LOG_PATH)  # the history is never left half-written
            return removed
    except Exception as error:
        print(f'Could not forget past conversations: {error}')
        return 0


def copy_log_to_vault():
    """Once per install: puts exchanges only the log has (from before the vault) into the day
    notes, since search reads the notes. Only once, so one the user deletes in Obsidian stays
    deleted."""
    done = LOG_PATH + '.in-vault'
    if os.path.exists(done):
        return
    added = vault.copy_in_exchanges(_lines())
    if added:
        print(f'Copied {added} earlier exchanges into the vault.')
    try:
        with open(done, 'w', encoding='utf-8') as f:
            f.write('conversations.jsonl was copied into the vault day notes.\n')
    except OSError as error:
        print(f'Could not note that the log was copied: {error}')


def _text(item):
    return f"{item.get('you', '')}\n{item.get('jarvis', '')}"


def _words(text):
    return {w for w in WORD.findall(text.lower()) if len(w) >= 3}


def _in_range(item, since, until):
    t = item.get('t', '')
    return (not since or t >= since) and (not until or t[:len(until)] <= until)


def _show(item, limit=300):
    try:
        when = datetime.datetime.fromisoformat(item['t']).strftime('%a %d %b, %H:%M')
    except (KeyError, TypeError, ValueError):
        when = '?'
    return f"[{when}] You: {item.get('you', '')[:limit]} / JARVIS: {item.get('jarvis', '')[:limit]}"


def _fit(lines, budget):
    """As many of lines as fit in budget characters, joined by newlines."""
    kept, size = [], 0
    for line in lines:
        if size + len(line) + 1 > budget:
            break
        kept.append(line)
        size += len(line) + 1
    return kept


def _last_conversation(items):
    earlier = [item for item in items if item['conv'] != _current]
    if not earlier:
        return 'No earlier conversations.'
    conv = earlier[-1]['conv']
    header = 'Last conversation:'
    newest_first = [_show(item) for item in reversed(earlier) if item['conv'] == conv]
    kept = _fit(newest_first, MAX_CHARS - len(header) - 1)
    return '\n'.join([header] + list(reversed(kept)))


# ---- the vault, in pieces ------------------------------------------------------------------

def _split(text):
    """A paragraph as pieces of at most PIECE_CHARS, cut between words."""
    pieces, words = [], text.split()
    while words:
        piece = []
        while words and len(' '.join(piece + words[:1])) <= PIECE_CHARS:
            piece.append(words.pop(0))
        if not piece:  # one word longer than a piece
            piece.append(words.pop(0)[:PIECE_CHARS])
        pieces.append(' '.join(piece))
    return pieces


def _note_pieces(path, relative, memory_path):
    """The pieces of one note: (label, text, when). when is a local ISO time for a conversation
    exchange, '' for anything else."""
    with open(path, encoding='utf-8-sig') as f:
        lines = f.read().splitlines()
    if os.path.normcase(path) == os.path.normcase(memory_path):
        return [('Remembered', m.group(1), '') for m in map(vault.FACT.match, lines) if m]
    day = DAY_NOTE.match(os.path.basename(path))
    if day and os.path.basename(os.path.dirname(path)) == 'Conversations':
        pieces = []
        for block in vault._blocks(lines)[1]:
            minute = block[0][4:].strip()
            said = ' '.join(line.replace('**', '') for line in block[1:] if line.strip())
            try:
                when = datetime.datetime.fromisoformat(f'{day.group(1)}T{minute}')
            except ValueError:
                continue
            if said:
                pieces.append((f'{when:%a %d %b, %H:%M}', said, when.isoformat(timespec='minutes')))
        return pieces
    label = 'Note: ' + os.path.splitext(relative)[0].replace(os.sep, '/')
    paragraphs, current = [], []
    for line in lines + ['']:
        if line.strip():
            current.append(line.strip())
        elif current:
            paragraphs.append(' '.join(current))
            current = []
    return [(label, piece, '') for p in paragraphs if not p.startswith('#') for piece in _split(p)]


def _pieces():
    """Every piece of the vault, read fresh (unchanged notes come from _parsed). Hidden folders
    (Obsidian's settings, its trash) are skipped."""
    root = vault.root()
    memory_path = os.path.join(root, vault.FOLDER, 'Memory.md')
    pieces, seen = [], set()
    for folder, folders, files in os.walk(root):
        folders[:] = sorted(f for f in folders if not f.startswith('.'))
        for name in sorted(files):
            if not name.endswith('.md'):
                continue
            path = os.path.join(folder, name)
            seen.add(path)
            try:
                modified = os.path.getmtime(path)
                if _parsed.get(path, (None,))[0] != modified:
                    _parsed[path] = (modified, _note_pieces(path, os.path.relpath(path, root), memory_path))
            except (OSError, UnicodeDecodeError):
                continue  # a note that can't be read is skipped, not fatal
            pieces += _parsed[path][1]
    for path in set(_parsed) - seen:
        del _parsed[path]
    return pieces


def _key(text):
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


def _load_piece_vectors():
    try:
        import numpy as np
        with np.load(INDEX_PATH) as saved:
            _piece_vectors.update(zip((str(k) for k in saved['keys']), saved['vectors']))
    except (OSError, ValueError, KeyError):
        pass


def _vectors_for(pieces):
    """A vector for every piece, making (and saving) only the ones not in the index yet."""
    import numpy as np
    keys = [_key(text) for _label, text, _when in pieces]
    missing = {k: text for k, (_label, text, _when) in zip(keys, pieces) if k not in _piece_vectors}
    if missing:
        _piece_vectors.update(zip(missing, _embed(list(missing.values()))))
        current = set(keys)
        for k in [k for k in _piece_vectors if k not in current]:  # notes deleted or edited
            del _piece_vectors[k]
        try:
            temporary = INDEX_PATH + '.part.npz'
            np.savez(temporary, keys=np.array(list(_piece_vectors)),
                     vectors=np.array(list(_piece_vectors.values()), dtype=np.float32).reshape(-1, DIMENSIONS))
            os.replace(temporary, INDEX_PATH)
        except OSError as error:
            print(f'Could not save the memory index: {error}')
    return np.array([_piece_vectors[k] for k in keys], dtype=np.float32).reshape(-1, DIMENSIONS)


def _scores(query, pieces):
    """(score, piece) for each piece worth showing."""
    words = _words(query)

    def keyword(text):
        return len(words & _words(text)) / len(words) if words else 0.0

    if _model is not None and pieces:
        q = _embed([query])[0]
        vectors = _vectors_for(pieces)
        return [(float(vectors[n] @ q) + KEYWORD_WEIGHT * keyword(p[1]), p) for n, p in enumerate(pieces)]
    return [s for s in ((keyword(p[1]), p) for p in pieces) if s[0] > 0]


def _show_piece(piece, limit=400):
    label, text, _when = piece
    return f'[{label}] {text[:limit]}'


def search(query='', since='', until=''):
    """What Claude's recall tool returns. Empty query: the last conversation before this one.
    Otherwise the best matches in the vault, best first. since/until: local ISO dates or times;
    with either, only conversation exchanges in that time count."""
    with _lock:
        if not query.strip():
            return _last_conversation([item for item in _lines() if _in_range(item, since, until)])
        pieces = [p for p in _pieces()
                  if not (since or until) or (p[2] and _in_range({'t': p[2]}, since, until))]
        best = sorted(_scores(query, pieces), key=lambda s: s[0], reverse=True)[:BEST]
    if not best:
        return 'Nothing found in your memory.'
    return '\n'.join(_fit([_show_piece(p) for _s, p in best], MAX_CHARS))


def _embed(texts):
    """One normalised vector per text (mean of the model's token vectors)."""
    import numpy as np
    session, tokenizer = _model
    names = {i.name for i in session.get_inputs()}
    rows = []
    for start in range(0, len(texts), 32):
        encoded = tokenizer.encode_batch(texts[start:start + 32])
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        feed = {'input_ids': ids, 'attention_mask': mask, 'token_type_ids': np.zeros_like(ids)}
        tokens = session.run(None, {k: v for k, v in feed.items() if k in names})[0]
        vectors = (tokens * mask[..., None]).sum(1) / mask.sum(1, keepdims=True)
        rows.append(vectors / np.linalg.norm(vectors, axis=1, keepdims=True))
    return np.vstack(rows).astype(np.float32)


def download_model():
    """Downloads the search model (about 24 MB) into models/recall, once."""
    import requests
    os.makedirs(MODEL_DIR, exist_ok=True)
    for name, remote in MODEL_FILES.items():
        path = os.path.join(MODEL_DIR, name)
        if os.path.exists(path):
            continue
        response = requests.get(MODEL_URL + remote, timeout=120)
        response.raise_for_status()
        if name == 'model.onnx' and len(response.content) < MIN_MODEL_BYTES:
            raise ValueError('the download is not the search model')
        with open(path + '.part', 'wb') as f:
            f.write(response.content)
        os.replace(path + '.part', path)  # a cut-off download never looks finished


def _delete_model_files():
    for name in MODEL_FILES:
        try:
            os.remove(os.path.join(MODEL_DIR, name))
        except OSError:
            pass


def load(download=True):
    """Copies the old log into the vault (once), loads the search model and indexes the vault.
    Returns True when search is by meaning, False when it falls back to keywords."""
    global _model
    copy_log_to_vault()
    try:
        if download and not all(os.path.exists(os.path.join(MODEL_DIR, n)) for n in MODEL_FILES):
            download_model()
        try:
            import onnxruntime
            import tokenizers
            session = onnxruntime.InferenceSession(os.path.join(MODEL_DIR, 'model.onnx'),
                                                   providers=['CPUExecutionProvider'])
            tokenizer = tokenizers.Tokenizer.from_file(os.path.join(MODEL_DIR, 'tokenizer.json'))
        except Exception:
            _delete_model_files()  # a bad file would otherwise block the download for good
            raise
        tokenizer.enable_truncation(256)
        tokenizer.enable_padding()
        with _lock:
            _model = (session, tokenizer)
            _load_piece_vectors()
            pieces = _pieces()
            if pieces:
                _vectors_for(pieces)  # index the vault now, so the first search is quick
        try:
            os.remove(OLD_INDEX_PATH)
        except OSError:
            pass
        print(f'Memory search: by meaning, over {len(pieces)} pieces of the vault.')
        return True
    except Exception as error:
        with _lock:
            _model = None
        print(f'Memory search: by keywords ({error}).')
        return False


def warm_up():
    """Loads search by meaning in the background (downloading the model the first time)."""
    threading.Thread(target=load, daemon=True).start()
