import re
import sys
import hashlib
import sys


class file:
    def __init__(self, filename):
        self.filename = filename


class bytecode:
    def __init__(self, code):
        self.code = code

    def encode(self):
