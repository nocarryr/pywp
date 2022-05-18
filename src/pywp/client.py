from __future__ import annotations
import typing as tp
from urllib.parse import urlsplit, urlunsplit
import dataclasses
from dataclasses import dataclass
from pathlib import Path

import jsonfactory
import json


import requests

from .config import Config
from . import api_objects as api

# HrefLink = 'Link'|tp.Dict[str, str]
# HrefLinkList = tp.List[HrefLink]
# HrefMap = tp.Dict[str, HrefLinkList|Link]

AnyDict = tp.Dict[tp.Any, tp.Any]

class Client:
    def __init__(self, config:Config|None = None, config_file: Path|str|None = None):
        if config is None:
            config = Config.load(config_file)
        self.config = config
        self._session = None
        self.use_cache = False
        self.request_cache = {}
        self.load_cache()

    def load_cache(self):
        if not self.use_cache:
            return
        fn = Path('.') / 'request_cache.json'
        if fn.exists():
            data = json.loads(fn.read_text())
            self.request_cache.update(data)

    def save_response(self, url, data):
        if not self.use_cache:
            return
        if url in self.request_cache:
            return
        self.request_cache[url] = data
        fn = Path('.') / 'request_cache.json'
        fn.write_text(json.dumps(self.request_cache, indent=2))

    @property
    def session(self) -> requests.Session:
        s = self._session
        if s is None:
            s = self._session = requests.Session()
            s.headers.update(self.config.get_auth_headers())
            s.headers.update({'user-agent':'curl 7.40.0'})
        return s

    @property
    def base_url(self) -> str:
        return self.config.base_url

    def join_url(self, *args) -> str:
        path = '/'.join([arg.strip('/') for arg in args])
        return f'{self.base_url}/{path}'

    def get(
        self, path, return_response: bool = False, **kwargs
    ) -> tp.Tuple[AnyDict, requests.Response]|AnyDict:

        if '://' in path:
            sp = urlsplit(path)
            base_sp = urlsplit(self.base_url)
            if sp.netloc != base_sp.netloc:
                r = requests.get(path, **kwargs)
                r.raise_for_status()
                return r.json()
            # url = urlunsplit([base_sp.scheme, base_sp.netloc, base_sp.path, '', ''])
            url = path
        else:
            url = self.join_url(path)
        if self.use_cache and url in self.request_cache:
            return self.request_cache[url]
        r = self.session.get(url, **kwargs)
        r.raise_for_status()
        data = r.json()
        self.save_response(url, data)
        if return_response:
            return data, r
        return data

    def get_paginated(
        self, path, order_by: str|None = None, per_page: int = 10, **kwargs
    ) -> tp.Iterable[AnyDict]:

        req_kw = kwargs.copy()
        params = req_kw.setdefault('params', {})
        if order_by is not None:
            if order_by.startswith('-'):
                order = 'desc'
                order_by = order_by.lstrip('-')
            else:
                if order_by.startswith('+'):
                    order_by = order_by.lstrip('+')
                order = 'asc'
            params.update({'order':order, 'order_by':order_by})


        params.update({'per_page':per_page, 'page':1})
        has_more = True

        while has_more:
            # print(f'page: {params["page"]}')
            data, r = self.get(path, return_response=True, **req_kw)
            yield data
            total_objs = int(r.headers['X-WP-Total'])
            total_pages = int(r.headers['X-WP-TotalPages'])
            has_more = params['page'] < total_pages
            print(f'page={params["page"]}, {has_more=}, {total_objs=}, {total_pages=}')
            params['page'] += 1


    def get_taxonomies(self) -> api.Taxonomies:
        data = self.get('taxonomies')
        return api.Taxonomies.create(data.values())

    def get_taxonomy(self, name: str) -> api.Taxonomy:
        data = self.get(f'taxonomies/{name}')
        return api.Taxonomy.create(data)

    def get_posts(
        self, post_type: str = 'post',
        order_by: str|None = None, per_page: int = 10, **kwargs
    ) -> api.PostList:

        post_list = None
        for page in self.get_paginated(post_type, order_by, per_page, **kwargs):
            if post_list is None:
                post_list = api.PostList.create(page)
            else:
                post_list.extend(page)
        return post_list
