"""SwiftShot layer model — pure PIL/collections, no Qt or editor coupling.

Extracted from editor.py so the layer/history data model can be tested and
reasoned about independently of the (large) editor UI module.
"""

from collections import deque

from PIL import Image, ImageChops


class Layer:
    BLEND_MODES = ["Normal", "Multiply", "Screen", "Overlay", "Darken",
                   "Lighten", "Difference", "Color Dodge", "Color Burn"]

    def __init__(self, name="Layer", width=800, height=600, image=None):
        self.name = name
        self.visible = True
        self.opacity = 255
        self.blend_mode = "Normal"
        self.locked = False
        self.image = image.convert("RGBA") if image is not None else Image.new("RGBA", (width, height), (0, 0, 0, 0))
        # ── Layer mask ────────────────────────────────────────────────────────
        self.mask          = None    # PIL Image "L" — None means no mask
        self.mask_enabled  = True    # toggle without deleting
        self.editing_mask  = False   # True → paint strokes go to mask, not image
        # ── Layer effects (fx stack) ──────────────────────────────────────────
        self.effects       = []      # list of effect dicts (ordered, non-destructive)

    def copy(self):
        l = Layer(self.name + " copy")
        l.image = self.image.copy()
        l.visible = self.visible
        l.opacity = self.opacity
        l.blend_mode = self.blend_mode
        l.locked = self.locked
        if self.mask is not None:
            l.mask = self.mask.copy()
        l.mask_enabled = self.mask_enabled
        l.editing_mask = False   # never copy the "editing" state
        l.effects = [dict(fx) for fx in self.effects]  # deep copy effect dicts
        return l

    def add_mask(self, mode="white"):
        """Add a layer mask. mode: 'white'=fully visible, 'black'=fully hidden, 'selection'=from caller."""
        iw, ih = self.image.size
        if mode == "black":
            self.mask = Image.new("L", (iw, ih), 0)
        else:
            self.mask = Image.new("L", (iw, ih), 255)
        self.mask_enabled = True

    def apply_mask(self):
        """Bake the mask into the layer alpha and remove it."""
        if self.mask is None: return
        r, g, b, a = self.image.split()
        new_a = ImageChops.multiply(a, self.mask) if self.mask_enabled else a
        self.image = Image.merge("RGBA", (r, g, b, new_a))
        self.mask = None
        self.editing_mask = False

    def delete_mask(self):
        self.mask = None
        self.editing_mask = False

    def mask_from_selection(self, sel_mask):
        """Set mask from an L-mode selection mask."""
        iw, ih = self.image.size
        if sel_mask.size != (iw, ih):
            sel_mask = sel_mask.resize((iw, ih), Image.LANCZOS)
        self.mask = sel_mask.copy()
        self.mask_enabled = True

# ── History ───────────────────────────────────────────────────────────────────
class HistoryManager:
    # Default byte budget for the undo stack. A count cap alone let a few 4K
    # multi-layer snapshots pin gigabytes; this evicts the oldest history once
    # the estimated memory exceeds the budget.
    DEFAULT_MAX_BYTES = 512 * 1024 * 1024

    def __init__(self, max_states=30, max_bytes=None):
        self.undo_stack = deque(maxlen=max_states)
        self.redo_stack = deque(maxlen=max_states)
        self.max_bytes = max_bytes or self.DEFAULT_MAX_BYTES
        # Invoked on every mutation -- the editor uses it for dirty tracking.
        self.on_change = None

    def _notify(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    @staticmethod
    def _layer_bytes(l):
        # Estimate without compositing a group (accessing group.image flattens
        # its children -- expensive): use the group's own dimensions + children.
        total = 0
        if hasattr(l, "children"):
            total += getattr(l, "_w", 0) * getattr(l, "_h", 0) * 4
            for c in l.children:
                total += HistoryManager._layer_bytes(c)
        else:
            img = getattr(l, "image", None)
            if img is not None:
                total += img.width * img.height * 4
        m = getattr(l, "mask", None)
        if m is not None:
            total += m.width * m.height
        return total

    @staticmethod
    def _state_bytes(entry):
        (state, _label) = entry
        layers = state[0]
        return sum(HistoryManager._layer_bytes(l) for l in layers)

    def _enforce_budget(self):
        total = sum(self._state_bytes(e) for e in self.undo_stack)
        while len(self.undo_stack) > 1 and total > self.max_bytes:
            total -= self._state_bytes(self.undo_stack.popleft())

    def save_state(self, layers, active_index, label="Edit"):
        state = self._snap(layers, active_index)
        self.undo_stack.append((state, label))
        self.redo_stack.clear()
        self._enforce_budget()
        self._notify()

    def undo(self, current_layers, current_index):
        if not self.undo_stack: return None, None, None
        (restore, lbl) = self.undo_stack.pop()
        self.redo_stack.append((self._snap(current_layers, current_index), lbl))
        self._notify()
        return restore[0], restore[1], lbl

    def redo(self, current_layers, current_index):
        if not self.redo_stack: return None, None, None
        (restore, lbl) = self.redo_stack.pop()
        self.undo_stack.append((self._snap(current_layers, current_index), lbl))
        self._notify()
        return restore[0], restore[1], lbl

    @staticmethod
    def _copy_layer(l):
        # Layer.copy()/LayerGroup.copy() preserve image, mask, mask_enabled,
        # effects and group children -- everything undo must restore.
        # They append " copy" to names (duplicate-layer UX), so restore them
        # recursively (grandchildren of nested groups were renamed too).
        s = l.copy()
        HistoryManager._restore_names(l, s)
        return s

    @staticmethod
    def _restore_names(src, dst):
        dst.name = src.name
        if hasattr(src, "children") and hasattr(dst, "children"):
            for sc, dc in zip(src.children, dst.children):
                HistoryManager._restore_names(sc, dc)

    def _snap(self, layers, idx):
        return ([self._copy_layer(l) for l in layers], idx)

    def all_labels(self):
        return [lbl for (_, lbl) in self.undo_stack]


class LayerGroup(Layer):
    """A layer that contains child layers composited together."""

    def __init__(self, name="Group", width=800, height=600):
        # Don't call Layer.__init__ image creation — we compute image from children
        self.name         = name
        self.visible      = True
        self.opacity      = 255
        self.blend_mode   = "Normal"
        self.locked       = False
        self.mask         = None
        self.mask_enabled = True
        self.editing_mask = False
        self.effects      = []
        self.children     = []   # list of Layer objects
        self.collapsed    = False
        self._w           = width
        self._h           = height

    @property
    def image(self):
        """Composite children into a single RGBA image (live)."""
        result = Image.new("RGBA", (self._w, self._h), (0, 0, 0, 0))
        for child in self.children:
            if not child.visible: continue
            img = child.image.copy()
            if child.mask is not None and child.mask_enabled:
                r, g, b, a = img.split()
                img = Image.merge("RGBA", (r, g, b, ImageChops.multiply(a, child.mask)))
            if child.opacity < 255:
                r, g, b, a = img.split()
                a = a.point(lambda x: int(x * child.opacity / 255))
                img = Image.merge("RGBA", (r, g, b, a))
            # alpha_composite, not paste(img, mask=img): pasting with the image
            # as its own mask multiplies alpha by itself (a 50%-opacity child
            # renders at 25% and soft edges darken). Proper source-over blend.
            result = Image.alpha_composite(result, img)
        return result

    @image.setter
    def image(self, val):
        pass  # groups don't have a pixel buffer to set directly

    def copy(self):
        g = LayerGroup(self.name + " copy", self._w, self._h)
        g.visible      = self.visible
        g.opacity      = self.opacity
        g.blend_mode   = self.blend_mode
        g.locked       = self.locked
        g.effects      = [dict(fx) for fx in self.effects]
        g.collapsed    = self.collapsed
        g.children     = [c.copy() for c in self.children]
        if self.mask: g.mask = self.mask.copy()
        g.mask_enabled = self.mask_enabled
        return g
