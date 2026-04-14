from django import template

register = template.Library()


def _merge_attrs(field, css=None, extra_attrs=None):
    if not hasattr(field, "field") or not hasattr(field, "as_widget"):
        return field
    attrs = {}
    existing = field.field.widget.attrs.get("class", "")
    if css:
        attrs["class"] = f"{existing} {css}".strip()
    if extra_attrs:
        attrs.update(extra_attrs)
    return field.as_widget(attrs=attrs)


@register.simple_tag
def render_field(field, css="", placeholder=None):
    attrs = {}
    if placeholder is not None:
        attrs["placeholder"] = placeholder
    return _merge_attrs(field, css=css, extra_attrs=attrs)


@register.filter
def add_class(field, css):
    return _merge_attrs(field, css=css)


@register.filter
def set_attr(field, attr):
    """
    Usage:
      {{ field|set_attr:"placeholder:Your text" }}
      {{ field|set_attr:"autocomplete:off" }}
    """
    if not hasattr(field, "field") or not hasattr(field, "as_widget"):
        return field
    if ":" not in attr:
        return field
    key, value = attr.split(":", 1)
    return _merge_attrs(field, extra_attrs={key: value})


@register.filter
def widget_type(field):
    if not hasattr(field, "field"):
        return ""
    return field.field.widget.__class__.__name__.lower()

