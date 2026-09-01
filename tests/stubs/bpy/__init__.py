"""Minimal bpy stub so MedBlend modules can be imported outside Blender."""


class _Namespace:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __getattr__(self, name):
        return _Namespace()

    def __call__(self, *a, **k):
        return _Namespace()


class _PropertyDeferred:
    """Stand-in for the object ``bpy.props.*`` returns.

    Blender registers properties by walking a class's ``__annotations__`` and
    ignoring anything that is not one of these, so the stub returns a
    recognisable object rather than ``None`` - a test can then tell a real
    property declaration apart from a stringified (PEP 563) annotation.
    """

    def __init__(self, kind, **keywords):
        self.kind = kind
        self.keywords = keywords

    def __repr__(self):
        return f"_PropertyDeferred({self.kind})"


def _deferred(kind):
    return staticmethod(lambda **k: _PropertyDeferred(kind, **k))


class props:
    StringProperty = _deferred("String")
    BoolProperty = _deferred("Bool")
    FloatProperty = _deferred("Float")
    IntProperty = _deferred("Int")
    EnumProperty = _deferred("Enum")
    CollectionProperty = _deferred("Collection")
    PointerProperty = _deferred("Pointer")


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

    class PropertyGroup(_Base):
        pass

    class Material(_Base):
        pass

    class Scene(_Base):
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
