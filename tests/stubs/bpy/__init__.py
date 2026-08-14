"""Minimal bpy stub so MedBlend modules can be imported outside Blender."""


class _Namespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __getattr__(self, name):
        return _Namespace()

    def __call__(self, *a, **k):
        return _Namespace()


class _Prop:
    def __call__(self, **kwargs):
        return None


class props:
    StringProperty = staticmethod(lambda **k: None)
    BoolProperty = staticmethod(lambda **k: None)
    FloatProperty = staticmethod(lambda **k: None)
    IntProperty = staticmethod(lambda **k: None)
    EnumProperty = staticmethod(lambda **k: None)
    CollectionProperty = staticmethod(lambda **k: None)
    PointerProperty = staticmethod(lambda **k: None)


class _Base:
    pass


class types:
    class AddonPreferences(_Base):
        pass

    class Panel(_Base):
        pass

    class Operator(_Base):
        pass

    class Object(_Base):
        pass

    class Modifier(_Base):
        pass

    class Volume(_Base):
        pass

    class Mesh(_Base):
        pass


class _Collection(list):
    def get(self, name, default=None):
        return default

    def new(self, *a, **k):
        return _Namespace()

    def load(self, *a, **k):
        return _Namespace()


class data:
    objects = _Collection()
    materials = _Collection()
    node_groups = _Collection()
    meshes = _Collection()
    volumes = _Collection()


class app:
    tempdir = "/tmp"
    cachedir = "/tmp"


context = _Namespace()
ops = _Namespace()


class path:
    @staticmethod
    def abspath(value):
        return value


class utils:
    @staticmethod
    def register_class(cls):
        pass

    @staticmethod
    def unregister_class(cls):
        pass
