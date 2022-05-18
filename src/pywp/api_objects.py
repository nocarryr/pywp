from __future__ import annotations
import typing as tp
from urllib.parse import urlsplit, urlunsplit
import dataclasses
from dataclasses import dataclass
from pathlib import Path
import datetime
import enum

import jsonfactory

__all__ = (
    'Taxonomies', 'Taxonomy', 'WpItems', 'WpItem',
    'HrefLink', 'HrefLinkList', 'HrefMap',
)

UTC = datetime.timezone.utc


HrefLink = tp.Union['Link', tp.Dict[str, str]]
HrefLinkList = tp.List[HrefLink]
HrefMap = tp.Dict[str, tp.Union[HrefLinkList, 'Link']]

def parse_wp_dt(dt_str: str) -> datetime.datetime:
    dt_fmt = '%Y-%m-%dT%H:%M:%S'
    dt = datetime.datetime.strptime(dt_str, dt_fmt)
    return datetime.datetime.replace(dt, tzinfo=UTC)

class Status(enum.Enum):
    publish = enum.auto()
    future = enum.auto()
    draft = enum.auto()
    pending = enum.auto()
    private = enum.auto()

    @classmethod
    def create(cls, value: str|'Status') -> 'Status':
        if isinstance(value, str):
            value = getattr(cls, value.lower())
        return value




@dataclass
class JsonBase:
    # links: HrefMap
    _child_object_attrs: tp.ClassVar[tp.List[str]] = []
    @classmethod
    def create(cls, data: tp.Dict[str, tp.Any]) -> 'JsonBase':
        return cls(**data)

    @classmethod
    def _deserialize(cls, data, decoder) -> 'JsonBase':
        # attrs = data.pop('_child_object_attrs', [])
        # assert not len(attrs)
        clsname = data.pop('__class__')
        assert clsname.split('.')[-1] == cls.__qualname__
        return cls(**data)

    @classmethod
    def _iter_subclasses(cls) -> tp.Iterator[type]:
        yield cls
        for subcls in cls.__subclasses__():
            yield from subcls._iter_subclasses()

    def _serialize(self) -> tp.Dict[tp.Any, tp.Any]:
        d = dataclasses.asdict(self)
        # d['_child_object_attrs'] = self._child_object_attrs.copy()
        return d

    def to_json(self, **kwargs):
        return jsonfactory.dumps(self, **kwargs)

    def save_to_json(self, filename: str|Path, **kwargs):
        if not isinstance(filename, Path):
            filename = Path(filename)
        filename.write_text(self.to_json(**kwargs))

@dataclass
class HasLinks(JsonBase):
    # links = Links
    _links: HrefMap
    # @classmethod
    # def create(cls, data: tp.Dict[str, tp.Any]) -> 'HasLinks':
    #     if 'links' not in data:
    #         links = data.pop('_links', {})
    #         data['links'] = Links(links)
    #     return super().create(data)

@dataclass
class WpItem(HasLinks):
    id: str
    count: int
    description: str
    link: str
    name: str
    slug: str
    taxonomy: str
    parent: int
    meta: tp.List[tp.Any]
    acf: tp.List[tp.Any]
    yoast_head: tp.Dict[tp.Any, tp.Any]
    yoast_head_json: tp.Dict[tp.Any, tp.Any]

@dataclass
class ItemContainer(JsonBase):
    items_by_id: tp.Dict[tp.Any, tp.Any]
    item_slug_map: tp.Dict[str, int]
    item_indices: tp.List[str]
    item_class: tp.ClassVar[type]

    @classmethod
    def create(cls, data: tp.List[tp.Dict[str, tp.Any]]) -> 'ItemContainer':
        # by_id, slug_map, indices = {}, {}, []
        kw = dict(items_by_id={}, item_slug_map={}, item_indices=[])
        # if isinstance(data, dict):
        #     data = data.values()
        for item_data in data:
            item = cls.create_child(item_data)
            item_id = cls._id_for_item(item)
            kw['items_by_id'][item_id] = item
            assert item.slug not in kw['item_slug_map']
            kw['item_slug_map'][item.slug] = item_id
            kw['item_indices'].append(item_id)
        return super().create(kw)

    @classmethod
    def create_child(cls, data: tp.Dict[str, tp.Any]) -> JsonBase:
        return cls.item_class.create(data)

    @classmethod
    def _deserialize(cls, data, decoder) -> 'ItemContainer':
        by_id = data['items_by_id']
        data['items_by_id'] = {}
        for key, val in by_id.items():
            obj = decoder.decoder(val)
            data['items_by_id'][key] = obj
        return super()._deserialize(data, decoder)

    @classmethod
    def _id_for_item(cls, item):
        raise NotImplementedError

    def append(self, child: JsonBase|tp.Dict[str, tp.Any]) -> JsonBase:
        if not isinstance(child, self.item_class):
            child = self.create_child(child)
        item_id = self._id_for_item(child)
        assert child.slug not in self.item_slug_map
        self.items_by_id[item_id] = child
        self.item_slug_map[child.slug] = item_id
        self.item_indices.append(item_id)
        return child

    def extend(self, children: tp.Sequence[JsonBase|tp.Dict[str, tp.Any]]):
        for item in children:
            self.append(item)

    def get_by_id(self, id_: int, default: tp.Any = None) -> tp.Any:
        return self.items_by_id.get(id_, default)

    def get_by_slug(self, slug: str, default: tp.Any = None) -> tp.Any:
        id_ = self.item_slug_map.get(slug)
        if id_ is None:
            return default
        return self.get_by_id(id_, default)

    def get_by_index(self, ix: int) -> JsonBase:
        id_ = self.item_indices[ix]
        return self.items_by_id[id_]

    def __len__(self) -> int:
        return len(self.items_by_id)

    def __iter__(self):
        yield from self.items_by_id.values()

@dataclass
class ItemList(ItemContainer):
    def __getitem__(self, key) -> 'JsonBase':
        ids = self.item_indices[key]
        if isinstance(ids, list):
            return [self.items_by_id[id_] for id_ in ids]
        return self.items_by_id[ids]

    def __iter__(self):
        for ix in self.item_indices:
            yield self[ix]

@dataclass
class ItemDict(ItemContainer):
    def __getitem__(self, key) -> 'JsonBase':
        return self.items_by_id[key]

    def keys(self): return self.items_by_id.keys()
    def values(self): return self.items_by_id.values()
    def items(self): return self.items_by_id.items()

    def __iter__(self):
        yield from self.values()

@dataclass
class WpItems(ItemList):
    items_by_id: tp.Dict[int, WpItem]
    item_class = WpItem

    @classmethod
    def _id_for_item(cls, item: WpItem) -> int:
        return item.id

@dataclass
class Taxonomy(HasLinks):
    name: str
    description: str
    slug: str
    types: tp.List[str]
    hierarchical: bool
    rest_base: str
    rest_namespace: str

    def get_items(self, client: 'pywp.client.Client') -> WpItems:
        item_url = self._links['wp:items'][0]['href']
        items = None
        for page in client.get_paginated(item_url):
            if items is None:
                items = WpItems.create(page)
            else:
                items.extend(page)
        return items

@dataclass
class Taxonomies(ItemDict):
    items_by_id: tp.Dict[str, Taxonomy]
    item_class = Taxonomy

    @classmethod
    def _id_for_item(cls, item: Taxonomy) -> str:
        return item.slug

@dataclass
class PostTaxonomyRel(JsonBase):
    taxonomy: str
    term_id: int
    term_slug: str


@dataclass
class Post(HasLinks):
    id: int
    pub_date: datetime.datetime
    last_modified: datetime.datetime
    slug: str
    status: Status
    type: str
    link: str
    title: str
    author: int
    taxonomy_names: tp.List[str]
    taxonomy_rels: tp.Dict[str, PostTaxonomyRel]

    @classmethod
    def create(cls, data: tp.Dict[str, tp.Any]) -> 'Post':
        keys = ['id', 'slug', 'type', 'link', 'title', 'author', '_links']
        kw = {key:data[key] for key in keys}
        kw['pub_date'] = parse_wp_dt(data['date_gmt'])
        kw['last_modified'] = parse_wp_dt(data['modified_gmt'])
        kw['status'] = Status.create(data['status'])
        kw['taxonomy_names'] = list(cls.get_taxonomy_names(data))
        kw['taxonomy_rels'] = {t:[] for t in kw['taxonomy_names']}
        return super().create(kw)

    @classmethod
    def get_taxonomy_names(cls, data: tp.Dict[str, tp.Any]) -> tp.Iterable[PostTaxonomyRel]:
        link_data = data['_links']
        terms = link_data.get('wp:term', [])
        for term in terms:
            if not term.get('embeddable'):
                continue
            yield term['taxonomy']

    @classmethod
    def _deserialize(cls, data, decoder) -> 'Post':
        data['status'] = decoder.decode(data['status'])
        for key in ['pub_date', 'last_modified']:
            dt = decoder.decode(data[key])
            data[key] = dt
        rels = decoder.decode(data['taxonomy_rels'])
        data['taxonomy_rels'] = rels
        return super()._deserialize(data, decoder)


    def check_taxonomy_rels(self, client):
        for taxonomy in self.taxonomy_names:
            rels = self.taxonomy_rels[taxonomy] = []
            url = f'{taxonomy}?post={self.id}&_fields=id,slug'
            data = client.get(url)
            if not len(data):
                continue
            for rel_data in data:
                rel = PostTaxonomyRel(
                    taxonomy=taxonomy,
                    term_id=rel_data['id'],
                    term_slug=rel_data['slug'],
                )
                rels.append(rel)


@dataclass
class PostList(ItemList):
    items_by_id: tp.Dict[int, Post]
    item_class = Post

    @classmethod
    def _id_for_item(cls, item: Post) -> int:
        return item.id

    def check_taxonomy_rels(self, client):
        for item in self:
            item.check_taxonomy_rels(client)


@jsonfactory.register
class JsonHandler:
    dt_fmt = '%Y-%m-%dT%H:%M:%SZ'
    def cls_to_str(self, cls):
        if type(cls) is not type:
            cls = cls.__class__
        return '.'.join([cls.__module__, cls.__qualname__])
    def str_to_cls(self, s):
        cls = Status
        if self.cls_to_str(cls) == s:
            return cls
        for cls in JsonBase._iter_subclasses():
            if self.cls_to_str(cls) == s:
                return cls
    def encode(self, o):
        if isinstance(o, JsonBase):
            d = o._serialize()
            d['__class__'] = self.cls_to_str(o)
            return d
        elif isinstance(o, Status):
            d = {
                '__class__':self.cls_to_str(o),
                'name':o.name, 'value':o.value,
            }
            return d
        elif isinstance(o, datetime.datetime):
            assert o.tzinfo is not None
            o = o.astimezone(UTC)
            d = {
                '__class__':'datetime.datetime',
                'value':o.strftime(self.dt_fmt),
            }
            return d
    def decode(self, d):
        if '__class__' in d:
            if cls == 'datetime.datetime':
                dt = datetime.datetime.strptime(d['value'], self.dt_fmt)
                dt = datetime.datetime.replace(dt, tzinfo=UTC)
                return dt
            cls = self.str_to_cls(d['__class__'])
            if cls is not None:
                if cls is Status:
                    return Status.create(d['name'])
                return cls._deserialize(d, self)
        return d
