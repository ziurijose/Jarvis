"""Past conversations. Every exchange is written down (conversations.jsonl), so Claude can
forget a conversation when it ends and still look it up when the user asks ("what were we
just talking about?", "what was that restaurant I mentioned?").

Search is by meaning, with a small on-device model (all-MiniLM-L6-v2, about 23 MB, run with
onnxruntime and tokenizers, which the voice and wake word already need). Until the model is
there, or if it can't load, search matches keywords instead.
"""
import datetime
import json
import os
import re
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, 'conversations.jsonl')
INDEX_PATH = os.path.join(HERE, 'recall_index.npy')
MODEL_DIR = os.path.join(HERE, 'models', 'recall')
MODEL_URL = 'https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/'
MODEL_FILES = {'model.onnx': 'onnx/model_quantized.onnx', 'tokenizer.json': 'tokenizer.json'}
DIMENSIONS = 384
MIN_MODEL_BYTES = 100_000  # a real model is megabytes; an error page is a few KB
MAX_CHARS = 1500  # what one recall may add to Claude's context
BEST = 8
KEYWORD_WEIGHT = 0.1  # added to meaning similarity (0 to 1), so exact names and numbers still win
WORD = re.compile(r"[a-z0-9']+")

_lock = threading.RLock()
_current = None   # this conversation's number
_model = None     # (onnxruntime session, tokenizer) once loaded
_vectors = None   # numpy array; row N is exchange N of _lines()


def use_folder(folder, model_dir=None):
    """Keeps conversations in another folder (tests use a temporary one)."""
    global LOG_PATH, INDEX_PATH, MODEL_DIR, _current, _model, _vectors
    with _lock:
        LOG_PATH = os.path.join(folder, 'conversations.jsonl')
        INDEX_PATH = os.path.join(folder, 'recall_index.npy')
        MODEL_DIR = model_dir or os.path.join(folder, 'models', 'recall')
        _current, _model, _vectors = None, None, None


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
            if _model is not None:
                _sync_index(_lines())
    except Exception as error:
        print(f'Could not write the conversation down: {error}')


def forget(about):
    """Removes every exchange that mentions about (any capitals), and returns how many went.
    Never raises, like record."""
    global _vectors
    needle = about.strip().lower()
    if not needle:
        return 0
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
                _vectors = None
                if _model is not None:
                    _sync_index(_lines())
            return removed
    except Exception as error:
        print(f'Could not forget past conversations: {error}')
        return 0


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


def _scores(query, items, chosen):
    """(score, position, item) for each chosen (position, item)."""
    words = _words(query)

    def keyword(item):
        return len(words & _words(_text(item))) / len(words) if words else 0.0

    if _model is not None and _vectors is not None and len(_vectors) == len(items):
        q = _embed([query])[0]
        return [(float(_vectors[n] @ q) + KEYWORD_WEIGHT * keyword(item), n, item) for n, item in chosen]
    return [s for s in ((keyword(item), n, item) for n, item in chosen) if s[0] > 0]


def search(query='', since='', until=''):
    """What Claude's recall tool returns. Empty query: the last conversation before this one.
    Otherwise the best-matching exchanges, best first. since/until: local ISO dates or times."""
    with _lock:
        items = _lines()
        chosen = [(n, item) for n, item in enumerate(items) if _in_range(item, since, until)]
        if not query.strip():
            return _last_conversation([item for _n, item in chosen])
        best = sorted(_scores(query, items, chosen), key=lambda s: (s[0], s[1]), reverse=True)[:BEST]
    if not best:
        return 'Nothing found in earlier conversations.'
    return '\n'.join(_fit([_show(item) for _s, _n, item in best], MAX_CHARS))


def _sync_index(items):
    """Gives every exchange without a vector one, and saves the index. Needs the model."""
    global _vectors
    import numpy as np
    stale = (_vectors is None or _vectors.ndim != 2 or _vectors.shape[1] != DIMENSIONS
             or len(_vectors) > len(items))  # lines were removed or the file was replaced
    if stale:
        _vectors = np.zeros((0, DIMENSIONS), dtype=np.float32)
    missing = items[len(_vectors):]
    if missing:
        _vectors = np.vstack([_vectors, _embed([_text(item) for item in missing])])
        try:
            np.save(INDEX_PATH, _vectors)
        except OSError as error:
            print(f'Could not save the conversation index: {error}')


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
    """Loads the search model and catches the index up. Returns True when search is by
    meaning, False when it falls back to keywords."""
    global _model, _vectors
    try:
        if download and not all(os.path.exists(os.path.join(MODEL_DIR, n)) for n in MODEL_FILES):
            download_model()
        import numpy as np
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
            try:
                _vectors = np.load(INDEX_PATH)
            except (OSError, ValueError):
                _vectors = None
            _sync_index(_lines())
        print('Conversation search: by meaning.')
        return True
    except Exception as error:
        with _lock:
            _model = None
        print(f'Conversation search: by keywords ({error}).')
        return False


def warm_up():
    """Loads search by meaning in the background (downloading the model the first time)."""
    threading.Thread(target=load, daemon=True).start()
