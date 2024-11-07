import re

class BTFailure(Exception):
    pass

def decode_int(x, f):
    f += 1
    newf = x.index(b'e', f)
    n = int(x[f:newf])
    if x[f] == ord('-'):
        if x[f + 1] == ord('0'):
            raise ValueError
    elif x[f] == ord('0') and newf != f + 1:
        raise ValueError
    return n, newf + 1

def decode_string(x, f):
    colon = x.index(b':', f)
    n = int(x[f:colon])
    if x[f] == ord('0') and colon != f + 1:
        raise ValueError
    colon += 1
    return x[colon:colon + n], colon + n

def decode_list(x, f):
    r, f = [], f + 1
    while x[f] != ord('e'):
        v, f = decode_func[x[f]](x, f)
        r.append(v)
    return r, f + 1

def decode_dict(x, f):
    r, f = {}, f + 1
    while x[f] != ord('e'):
        k, f = decode_string(x, f)
        r[k], f = decode_func[x[f]](x, f)
    return r, f + 1

decode_func = {
    ord('l'): decode_list,
    ord('d'): decode_dict,
    ord('i'): decode_int
}
for i in range(ord('0'), ord('9') + 1):
    decode_func[i] = decode_string

def bdecode(x):
    try:
        r, l = decode_func[x[0]](x, 0)
    except (IndexError, KeyError, ValueError):
        raise BTFailure("not a valid bencoded string")
    if l != len(x):
        raise BTFailure("invalid bencoded value (data after valid prefix)")
    return r


class Bencached:
    __slots__ = ['bencoded']

    def __init__(self, s):
        self.bencoded = s

def encode_bencached(x, r):
    r.append(x.bencoded)

def encode_int(x, r):
    r.extend((b'i', str(x).encode('utf-8'), b'e'))

def encode_bool(x, r):
    encode_int(1 if x else 0, r)

def encode_string(x, r):
    x = x.encode('utf-8') if isinstance(x, str) else x
    r.extend((str(len(x)).encode('utf-8'), b':', x))

def encode_list(x, r):
    r.append(b'l')
    for i in x:
        encode_func[type(i)](i, r)
    r.append(b'e')

def encode_dict(x, r):
    r.append(b'd')
    ilist = sorted(x.items())
    for k, v in ilist:
        k = k.encode('utf-8') if isinstance(k, str) else k
        r.extend((str(len(k)).encode('utf-8'), b':', k))
        encode_func[type(v)](v, r)
    r.append(b'e')

encode_func = {
    Bencached: encode_bencached,
    int: encode_int,
    bool: encode_bool,
    str: encode_string,
    bytes: encode_string,
    list: encode_list,
    tuple: encode_list,
    dict: encode_dict
}

def bencode(x):
    r = []
    encode_func[type(x)](x, r)
    return b''.join(r)
