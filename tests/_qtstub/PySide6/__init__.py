import sys, types
class _Meta(type):
    def __getattr__(cls, n):
        if n.startswith("__"): raise AttributeError(n)
        return Stub()
    def __or__(cls, o): return Stub()
class Stub(metaclass=_Meta):
    def __init__(self, *a, **k): pass
    def __getattr__(self, n):
        if n.startswith("__") and n.endswith("__"): raise AttributeError(n)
        # eigene Klassen (nicht Qt): unbekannte Python-Namen (_privat, snake_case) sind echte Fehler
        if type(self).__module__.split(".")[0] != "PySide6" and not (n.endswith("_") and not n.startswith("_")) \
                and (n.startswith("_") or ("_" in n and n.lower() == n)):
            raise AttributeError(f"{type(self).__name__} hat kein Attribut {n!r}")
        return Stub()
    def __call__(self, *a, **k): return Stub()
    def __iter__(self): return iter(())
    def __len__(self): return 0
    def __bool__(self): return True
    def __int__(self): return 0
    def __float__(self): return 0.0
    def __index__(self): return 0
    def __hash__(self): return 1
    def __eq__(self, o): return isinstance(o, Stub)
    def __str__(self): return ""
    def __getitem__(self, k): return Stub()
    def __contains__(self, k): return False
for _op in ("add","sub","mul","truediv","floordiv","mod","or","and","xor","lt","le","gt","ge","neg","pos","abs"):
    pass
def _num(self, *a): return 0
for _op in ("__add__","__radd__","__sub__","__rsub__","__mul__","__rmul__","__truediv__","__rtruediv__","__floordiv__",
            "__mod__","__neg__","__pos__","__abs__","__lt__","__le__","__gt__","__ge__","__round__"):
    setattr(Stub, _op, _num)
for _op in ("__or__","__ror__","__and__","__rand__","__xor__","__invert__"):
    setattr(Stub, _op, lambda self, *a: Stub())
class _Bound:
    def __init__(self): self.f=[]
    def connect(self, f, *a): self.f.append(f)
    def emit(self, *a):
        for f in self.f: f(*a)
    def disconnect(self, *a): pass
class Signal:
    def __init__(self, *a, **k): self.name=None
    def __set_name__(self, owner, name): self.name="_sig_"+name
    def __get__(self, obj, typ=None):
        if obj is None: return self
        d=obj.__dict__
        if self.name not in d: d[self.name]=_Bound()
        return d[self.name]
def Slot(*a, **k): return lambda f: f
class _Mod(types.ModuleType):
    def __getattr__(self, n):
        if n.startswith("__"): raise AttributeError(n)
        if n == "Signal": return Signal
        if n == "Slot": return Slot
        cls = _Meta(n, (Stub,), {})
        setattr(self, n, cls)
        return cls
for m in ("QtCore","QtGui","QtWidgets","QtSvg","QtNetwork","QtPrintSupport","QtSvgWidgets"):
    mod=_Mod("PySide6."+m); sys.modules["PySide6."+m]=mod; setattr(sys.modules[__name__], m, mod)
