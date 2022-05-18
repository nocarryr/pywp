from __future__ import annotations
import os
import typing as tp
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit
import base64

from dotenv import dotenv_values

DEFAULT_ENVFILE = Path.home() / '.pywp.env'

@dataclass
class Config:
    auth_user: str
    auth_pass: str
    base_url: str

    @classmethod
    def load(cls, config_file: str|Path|None) -> 'Config':
        if config_file is None:
            config_file = DEFAULT_ENVFILE
        elif not isinstance(config_file, Path):
            config_file = Path(config_file)
        data = {
            **dotenv_values(config_file),
            **os.environ,
        }
        fields = ['auth_user', 'auth_pass', 'base_url']
        data = {k:data.get(k.upper()) for k in fields}
        for field in fields:
            if data.get(field) is None:
                raise ValueError(f'No value found for "{field}"')
        base_url = data['base_url']
        sp = urlsplit(base_url)
        base_url = urlunsplit([sp.scheme, sp.netloc, '', '', ''])
        base_url = f'{base_url}/wp-json/wp/v2'
        data['base_url'] = base_url
        return cls(**data)

    def get_token(self) -> bytes:
        cred = ':'.join([self.auth_user, self.auth_pass])
        return base64.b64encode(cred.encode())

    def get_auth_headers(self) -> tp.Dict[str, str]:
        token = self.get_token().decode('utf-8')
        return {'Authorization':f'Basic {token}'}
