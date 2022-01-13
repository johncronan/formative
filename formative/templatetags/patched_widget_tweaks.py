import re
import types
from copy import copy
from django.template import Library, TemplateSyntaxError
from widget_tweaks.templatetags.widget_tweaks import silence_without_field, \
    ATTRIBUTE_RE, FieldAttributeNode

register = Library()


def _process_field_attributes(field, attr, process):
    params = re.split(r"(?<!:):(?!:)", attr, 1)
    attribute = params[0].replace("::", ":")
    value = params[1] if len(params) == 2 else True
    field = copy(field)

    if not hasattr(field, 'as_widget'):
        old_tag = field.tag

        def tag(self, wrap_label=False):
            attrs = self.data['attrs']
            process(self.parent_widget, attrs, attribute, value)
            html = old_tag(wrap_label=False)
            self.tag = old_tag
            return html

        field.tag = types.MethodType(tag, field)
        return field
    
    old_as_widget = field.as_widget

    def as_widget(self, widget=None, attrs=None, only_initial=False):
        attrs = attrs or {}
        process(widget or self.field.widget, attrs, attribute, value)
        if attribute == "type":
            self.field.widget.input_type = value
            del attrs["type"]
        html = old_as_widget(widget, attrs, only_initial)
        self.as_widget = old_as_widget
        return html

    field.as_widget = types.MethodType(as_widget, field)
    return field


@register.filter("attr")
@silence_without_field
def set_attr(field, attr):
    def process(widget, attrs, attribute, value):
        attrs[attribute] = value

    return _process_field_attributes(field, attr, process)


@register.filter("add_error_attr")
@silence_without_field
def add_error_attr(field, attr):
    if hasattr(field, "errors") and field.errors:
        return set_attr(field, attr)
    return field


@register.filter("append_attr")
@silence_without_field
def append_attr(field, attr):
    def process(widget, attrs, attribute, value):
        if attrs.get(attribute):
            attrs[attribute] += " " + value
        elif widget.attrs.get(attribute):
            attrs[attribute] = widget.attrs[attribute] + " " + value
        else:
            attrs[attribute] = value

    return _process_field_attributes(field, attr, process)


@register.filter("add_class")
@silence_without_field
def add_class(field, css_class):
    return append_attr(field, "class:" + css_class)


@register.tag
def render_field(parser, token):
    error_msg = (
        '%r tag requires a form field followed by a list of '
        'attributes and values in the form attr="value"'
        % token.split_contents()[0]
    )
    try:
        bits = token.split_contents()
        tag_name = bits[0]  # noqa
        form_field = bits[1]
        attr_list = bits[2:]
    except ValueError:
        raise TemplateSyntaxError(error_msg)

    form_field = parser.compile_filter(form_field)

    set_attrs = []
    append_attrs = []
    for pair in attr_list:
        match = ATTRIBUTE_RE.match(pair)
        if not match:
            raise TemplateSyntaxError(error_msg + ": %s" % pair)
        dct = match.groupdict()
        attr, sign, value = (
            dct["attr"],
            dct["sign"],
            parser.compile_filter(dct["value"]),
        )
        if sign == "=":
            set_attrs.append((attr, value))
        else:
            append_attrs.append((attr, value))

    return FieldAttributeNode(form_field, set_attrs, append_attrs)
